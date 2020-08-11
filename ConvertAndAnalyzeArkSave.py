import subprocess
import naya
import sys
import re
import os
import time
from pprint import pprint


# Global variables hold the sorted game objects ahead of reporting.
owners = dict()
inventories = dict()
itemstacks = dict()
miscellaneous = dict()
inventory_to_owner_reverse_lookup = dict()
tame_dinos = dict()
dino_status = dict()

def getPropertyValueByName(properties, name):
    for prop in properties:
        if prop['name'] == name:
            return prop['value']
    return ''

def getPropertyValueByNameAndIndex(properties, name, index):
    for prop in properties:
        if prop['name'] == name and prop.get('index', '') == index:
            return prop['value']
    return 0.0

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

    if ("InventoryComponent" in gameobject['class']):
        return "Inventory"

    if ("PrimalInventoryBP" in gameobject['class']):
        return "Inventory"

    if ("PrimalItem" in gameobject['class']):
        if (isEngram(gameobject)):
            return "Engram"
        else:
            return "ItemStack"

    for prop in gameobject.get('properties', {}):
        if prop['name'] == 'OwnerInventory':
            return "ItemStack"
        if prop['name'] == 'MyInventoryComponent':
            return "InventoryOwner"
        if prop['name'] == 'TamerString':
            return "TameDinosaur"

    if gameobject['class'].startswith("DinoCharacterStatusComponent") or \
       gameobject['class'].startswith("Mega_DinoCharacterStatusComponent"): 
        return "DinosaurStatus"

    if gameobject['class'].startswith("PlayerCharacterStatusComponent"):
        return "PlayerStatusComponent"

    if ("_Character_BP_C" in gameobject['class']):
        return "WildDinosaur"

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

    if (objtype == "TameDinosaur"):
        tame_dinos[gameobject['id']] = gameobject

    if (objtype == "DinosaurStatus"):
        dino_status[gameobject['id']] = gameobject


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

def report_hungry_tames(hungry_tames_filename):
    # Status values are an ordered sequence rather than named.
    # Constants help us stay sane.
    INDEX_FOOD = 4

    # Order from 0: Health, Stamina, Torpidity, Oxygen, Food, Water, 
    # Temperature, Weight, MeleeDamageMultiplier, SpeedMultiplier, 
    # TemperatureFortitude, CraftingSpeedMultiplier

    with open(hungry_tames_filename, "w") as outfile:
        # We're denormalizing here; producing a flat list out of hierarchical objects.
        header = "Dino\tLevel\tDino Name\tx\ty\tz\tFood Levelups\tFood Current\tFood Total\tTamerString\tPlayerName\tTribeName"
        outfile.write(header)

        for dino_id in tame_dinos:
            dino = tame_dinos[dino_id]
            status = dino_status[getPropertyValueByName(dino['properties'], 'MyCharacterStatusComponent')]

            food_current_value = getPropertyValueByNameAndIndex(status['properties'], "CurrentStatusValues", INDEX_FOOD)
            if not food_current_value:
                food_current_value = 0.0
            food_levelups_wild = getPropertyValueByNameAndIndex(status['properties'], "NumberOfLevelUpPointsApplied", INDEX_FOOD)
            if not food_levelups_wild:
                food_levelups_wild = 0.0
            food_levelups_tame = getPropertyValueByNameAndIndex(status['properties'], "NumberOfLevelUpPointsAppliedTamed", INDEX_FOOD)
            if not food_levelups_tame:
                food_levelups_tame = 0.0

            base_character_level = getPropertyValueByName(status['properties'], "BaseCharacterLevel")
            if not base_character_level:
                base_character_level = 0.0
            extra_character_level = getPropertyValueByName(status['properties'], "ExtraCharacterLevel")
            if not extra_character_level:
                extra_character_level = 0.0

            row = str(dino['id']) + \
                "\t" + str(simplifyName(dino['class'])) + \
                "\t" + str(base_character_level + extra_character_level) + \
                "\t" + str(getPropertyValueByName(dino['properties'], 'TamedName')) + \
                "\t" + str(dino['location']['x']) + \
                "\t" + str(dino['location']['y']) + \
                "\t" + str(dino['location']['z']) + \
                "\t" + str(food_levelups_wild + food_levelups_tame) + \
                "\t" + str(food_current_value) + \
                "\t" + "totalTBD" + \
                "\t" + str(getPropertyValueByName(dino['properties'], 'TamerString')) + \
                "\t" + str(getPropertyValueByName(dino['properties'], 'OwningPlayerName')) + \
                "\t" + str(getPropertyValueByName(dino['properties'], 'TribeName'))
            outfile.write(row + "\n")


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
    start_time_seconds = round(time.time())

    json_full_filename = ark_binary_filename.replace(".ark", ".json")
    json_objects_filename = ark_binary_filename.replace(".ark", "_game_objects.json")
    inventory_filename = ark_binary_filename.replace(".ark", "_inventory.txt")
    hungry_tames_filename = ark_binary_filename.replace(".ark", "_hungry_tames.txt")

    iprint("1/5 Converting {} from binary to json; this takes a minute...".format(ark_binary_filename))
    convert_binary_to_json(ark_binary_filename, json_full_filename)
    iprint("1/5 Wrote {}\n".format(json_full_filename))

    iprint("2/5 Simplifying json so we can read the game objects...")
    simplify_json_to_game_objects(json_full_filename, json_objects_filename)
    iprint("2/5 Wrote {}\n".format(json_objects_filename))

    iprint("3/5 Processing game objects. This takes the longest time; several minutes...")
    process_game_objects(json_objects_filename) # purely in-memory

    iprint("4/5 Reporting inventories...")
    report_inventories(inventory_filename)
    iprint("4/5 Wrote {}\n".format(inventory_filename))

    iprint("5/5 Reporting hungry tames...")
    report_hungry_tames(hungry_tames_filename)
    iprint("5/5 Wrote {}\n".format(hungry_tames_filename))

    end_time_seconds = round(time.time())

    #print("Unhandled types:")  # These have been verified as non-inventory as of July 2020.
    #pprint(miscellaneous)

    minutes = (end_time_seconds - start_time_seconds)/60.0
    iprint("Completed in " + str(minutes) + " minutes.")


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

