import subprocess
import naya
import sys
import re
import os
from pprint import pprint

# Global variables hold the sorted game objects ahead of reporting.
owners = dict()
inventories = dict()
itemstacks = dict()
miscellaneous = dict()
inventory_to_owner_reverse_lookup = dict()

def getPropertyValueByName(properties, name):
    for prop in properties:
        if prop['name'] == name:
            return prop['value']
    return ''

def isEngram(gameobject):
    if (not gameobject.get('properties', {})):
        return False
    for prop in gameobject['properties']:
        if prop['name'] == 'bIsEngram':
            return prop['value']
    return False

def isSpecialInventoryItem(gameobject):
    # default blueprints/engrams are generally hidden from inventory display
    if (not gameobject.get('properties', {})):
        return False
    for prop in gameobject['properties']:
        if prop['name'] == 'bAllowRemovalFromInventory':
            return not prop['value'] 
    return False

def identifyType(gameobject):
    if ("Tribute" in gameobject['class']):
        return "Obelisk_Related"

    if ("StatusComponent" in gameobject['class']):
        return "StatusComponent"

    if ("InventoryComponent" in gameobject['class']):
        return "Inventory"

    if ("PrimalInventoryBP" in gameobject['class']):
        return "Inventory"

    if ("PrimalItem" in gameobject['class']):
        if (isEngram(gameobject)):
            return "Engram"
        else:
            return "ItemStack"

    if ("_Character_BP_C" in gameobject['class']):
        return "CharacterBP"

    for prop in gameobject.get('properties', {}):
        if prop['name'] == 'OwnerInventory':
            return "ItemStack"
        if prop['name'] == 'MyInventoryComponent':
            return "InventoryOwner"

    return "miscellaneous"

def register_owner(owner):
    # Sometimes more than one owner points to the same
    # inventory, so we're creating a reverse lookup from
    # inventory to owners.  Key is inventoryComponentId; value is list [] of ownerIds.
    ownerId = owner['id']
    inventoryComponentId =  getPropertyValueByName(owner['properties'], 'MyInventoryComponent')
    if inventoryComponentId:
        ownerlist = inventory_to_owner_reverse_lookup.get(inventoryComponentId, [])
        ownerlist.append(ownerId)
        inventory_to_owner_reverse_lookup[inventoryComponentId] = ownerlist


def handle_object(gameobject):
    global owners, inventories, itemstacks
    objtype = identifyType(gameobject)

    if (objtype == "InventoryOwner"):
        owners[gameobject['id']] = gameobject
        register_owner(gameobject)

    if (objtype == "Inventory"):
        inventories[gameobject['id']] = gameobject

    if (objtype == "ItemStack"):
        itemstacks[gameobject['id']] = gameobject

    if (objtype == "miscellaneous"):
        miscellaneous[gameobject['class']] = miscellaneous.get(gameobject['class'], 0) + 1

def simplifyName(text):
    text = text.replace("PrimalInventoryBP_", "").replace("PrimalItemResource_", "").replace("PrimalItemConsumable_", "").replace("PrimalItem_", "").replace("PrimalItem", "")
    if text.endswith("_C"):
        text = text[:-2]
    return text


def report_inventories(inventory_filename):
    with open(inventory_filename, "w") as outfile:
        # We're denormalizing here; producing a flat list out of hierarchical objects.
        header = "OwnerID\tInventoryOwnerClass\tx\ty\tz\tOwnerName\tOwningPlayerName\tOwningTameName\tTribeName\tInventoryID\tInventoryClass\tInventoryStackItemType\tStackQuantity\tBlueprint\n"
        outfile.write(header)

        for inventoryComponentId in inventory_to_owner_reverse_lookup:
            inventoryObject = inventories.get(inventoryComponentId, None)
            if not inventoryObject:
                continue  # skip any we can't find which are usually leashes and other misclassified things.

            # Some inventories have more than one owner because of serialization quirks. They're 
            # all the same data except id, so literally just pick any instance if there are two or more.
            owner = owners[inventory_to_owner_reverse_lookup[inventoryComponentId][0]]

            identifierColumns = str(owner['id']) + \
                "\t" + simplifyName(owner['class']) + \
                "\t" + str(owner['location']['x']) + \
                "\t" + str(owner['location']['y']) + \
                "\t" + str(owner['location']['z']) + \
                "\t" + getPropertyValueByName(owner['properties'], 'OwnerName') + \
                "\t" + getPropertyValueByName(owner['properties'], 'OwningPlayerName')  + getPropertyValueByName(owner['properties'], 'PlayerName') + \
                "\t" + getPropertyValueByName(owner['properties'], 'TameName') + \
                "\t" + getPropertyValueByName(owner['properties'], 'TribeName') + \
                "\t" + str(inventoryObject['id']) + \
                "\t" + simplifyName(inventoryObject.get('class', ''))

            stackIds = getPropertyValueByName(inventoryObject['properties'], 'InventoryItems')
            stacks = dict()
            for stackId in stackIds:
                stack = itemstacks.get(stackId, None)
                if stack and not isEngram(stack) and not isSpecialInventoryItem(stack):
                    itemName = simplifyName(stack['class'])
                    itemQuantity = getPropertyValueByName(stack['properties'], 'ItemQuantity') or 1
                    bisBlueprint = str(getPropertyValueByName(stack['properties'], 'bIsBlueprint'))
                    outfile.write(identifierColumns + "\t" + itemName + "\t" + str(itemQuantity) + "\t" + ("Blueprint" if bisBlueprint else "Item") + "\n")
    return inventory_filename

def simplify_json_to_game_objects(json_full_filename, json_objects_filename):
    """
    The json that results from the binary->json conversion is more than we
    really want for the game objects processing.  The 'naya' library can
    very quickly process a stream of objects in an array, but not the full
    json.  Since we don't want to read the entire hefty file into memory
    at once, we'll pre-process it so that naya can handle it streaming instead.

    To do that, we have to pre-process to remove a layer of json.  
    The file is too big to do that easily by reading the json into 
    memory, so we'll do a lazy shortcut with python per-line reading.  
    This is sensitive to the exact format of the json file; don't change 
    spacing unless you fix this too.

    We're going to erase everything before and including the start line,
    then keep lines until we find the end line.  Then we have to modify
    the previous line written out (ugh) to remove the trailing comma and
    close the square brackets; so instead, we'll write out one behind the
    actual so we can do it sequentially without moving backwards.

    The result is [ { "id": 1 ...}, { "id": 2 ...} ] with just the array of
    game objects and not all the other stuff.
    """
    start_line = "  \"objects\": ["
    end_line   = "  \"hibernation\": {"

    previous_line = ""
    current_line = ""
    writing = False
    with open(json_objects_filename, 'w+') as outfile:
        with open(json_full_filename, 'r') as infile:
            for current_line in infile:
                if writing and not end_line.strip() == current_line.strip():
                    outfile.write(previous_line)
                if start_line.strip() == current_line.strip():
                    writing = True
                    outfile.write("[\n")
                    current_line=""
                if end_line.strip() == current_line.strip():
                    outfile.write("]\n") # instead of previous.
                    current_line=""
                    writing = False
                previous_line = current_line


def process_game_objects(json_objects_filename):
    """
    Reads the game objects json and pulls out text-format inventory etc.
    Stores this information in global variables for later reporting.
    """
    with open(json_objects_filename) as data:
        gameobjects = naya.stream_array(naya.tokenize(data))
        for gameobject in gameobjects:
            handle_object(gameobject)

def convert_binary_to_json(ark_binary_filename, json_full_filename):
    """
    This calls out to a helper C# app to convert binary to json,
    but that app expects the json file to not exist yet.  It'll give
    errors about duplicate keys if the json file already exists.
    """
    if os.path.isfile(json_full_filename) and os.path.exists(json_full_filename):
        os.remove(json_full_filename)
    returned_output = subprocess.check_output(["./ArkBinaryToJsonConvertor.exe", ark_binary_filename, json_full_filename]).decode("utf-8").strip()
    print(re.sub("^", "    ", returned_output, flags=re.MULTILINE)) # nice indent on output from subprocess

def iprint(text):
    """
    Prints a message to screen and immediately flushes the 
    write buffer so it shows up without waiting for more text.
    This provides timely updates to the end user.
    """
    print(text)
    sys.stdout.flush()

def main_conversion(ark_binary_filename):
    """
    The main entry point if you import this in a library; this
    will take a Map.ark file, convert it to json, process the
    json into in-memory sets, and report on the inventories.
    Output goes to similarly named files.
    """
    json_full_filename = ark_binary_filename.replace(".ark", ".json")
    json_objects_filename = ark_binary_filename.replace(".ark", "_game_objects.json")
    inventory_filename = ark_binary_filename.replace(".ark", "_inventory.txt")

    iprint("1/4 Converting {} from binary to json; this takes a minute...".format(ark_binary_filename))
    convert_binary_to_json(ark_binary_filename, json_full_filename)
    iprint("1/4 Wrote {}\n".format(json_full_filename))

    iprint("2/4 Simplifying json so we can read the game objects...")
    simplify_json_to_game_objects(json_full_filename, json_objects_filename)
    iprint("2/4 Wrote {}\n".format(json_objects_filename))

    iprint("3/4 Processing game objects. This takes the longest time; several minutes...")
    process_game_objects(json_objects_filename) # purely in-memory

    iprint("4/4 Reporting inventories...")
    report_inventories(inventory_filename)
    iprint("4/4 Wrote {}\n".format(inventory_filename))

    #print("Unhandled types:")  # These have been verified as non-inventory as of July 2020.
    #pprint(miscellaneous)

    iprint("Complete.")


def main(argv):
    if not len(argv) == 2:
        print("Missing input file command line argument.  Please provide a path to your input file.")
        print("Usage:\t    python ConvertAndAnalyzeArkSave.py path/to/TheIsland.ark")
        exit(1)
    ark_binary_filename = argv[1] # 0 is the script name
    main_conversion(ark_binary_filename)


# Actual entry point if run as a script; does not trigger automatically if imported as a library.
if __name__ == "__main__":
    main(sys.argv)

