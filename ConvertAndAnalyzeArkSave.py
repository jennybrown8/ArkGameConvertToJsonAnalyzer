import subprocess
import naya
import sys
import re
import os
import time
import json
from pprint import pprint


# Global variables hold the sorted game objects ahead of reporting.
owners = dict()
inventories = dict()
itemstacks = dict()
miscellaneous = dict()
inventory_to_owner_reverse_lookup = dict()
tame_dinos = dict()
dino_status = dict()

# Status values are an ordered sequence rather than named.
# Constants help us stay sane.
INDEX_FOOD = 4
PRIMALEARTH = "/Game/PrimalEarth/Dinos/"

# Order from zero: 0 Health, 1 Stamina, 2 Torpidity, 3 Oxygen, 4 Food, 5 Water, 
# 6 Temperature, 7 Weight, 8 MeleeDamageMultiplier, 9 SpeedMultiplier, 
# 10 TemperatureFortitude, 11 CraftingSpeedMultiplier

not_really_dinos = [
  "Raft_BP_C",
  "MotorRaft_BP_C",
  "Barge_BP_C",
  "CPCanoeBoat_eco_C",
  "IRaft_BP_C",
  "GalleonRaft_BP_C",
  "CogRaft_BP_C",
  "TekHoverSkiff_Character_BP_C",
  "BP_HoverSkiff_C"
]


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

def load_values_json():
    print("Loading values.json into memory")

    with open('values.json') as f:
        valuesdata = json.load(f)

    values_by_bp = dict()
    for species in valuesdata['species']:
        if PRIMALEARTH in species['blueprintPath']:
            shortname = species['blueprintPath'].split(".")[1]
            values_by_bp[shortname + "_C"] = species

    return values_by_bp



def calculate_food_total(dino, valuesjson_entry, base_character_level, extra_character_level, food_levelups_wild, food_levelups_tame):
    """
    Calculation formula for this is based on the excellent notes on Ark's wiki:
    https://ark.gamepedia.com/Creature_Stats_Calculation

    Reference data comes from the ArkSmartBreeding values.json - the file format
    is documented here: 
    https://github.com/cadon/ARKStatsExtractor/wiki/Mod-Values
    Under the fullStatsRaw, the order in a row is "Base (B), wildLevel (Iw), tamedLevel (Id), 
    tamingAdd (Ta), tamingAffinity (Tm?)"
    and the order of the rows should match the normal stat order for the 12 stats.
    """
    if not valuesjson_entry:
        print("Error! No json entry matched for dino of class " + dino['class'] + " -- check name matching logic.")
        return 0

    statusComponentId =  getPropertyValueByName(dino['properties'], 'MyCharacterStatusComponent')
    if not statusComponentId:
        print("Error! Couldn't find status component. Coding bug?")
        return 0

    statusComponent = dino_status[statusComponentId]


    # Calculation Example
    # In-game food total for tamed but not imprinted pteranodon: 4958.3
    # 29 wild level-ups in food
    # pteranodon is level 202
    # 
    # I think the character blueprints we're seeking are /Game/PrimalEarth/Dinos/ in values.json but not certain.
    # 
    # B - base value - from values.json
    # Lw - levels wild (input parameter above)
    # Ld - levels domestic (input parameter above)
    # Iw - increase wild: per-level wild increase as percent of B - from values.json (often looks like a lowercase l)
    # Id - increase domestic: per-level domestic increase as percent of B - from values.json (often looks like a lowercase l)
    # Ta - taming additive bonus - from values.json
    # Tm - taming multiplicative bonus - from values.json
    # TE - taming effectiveness (when tamed) - must be from dino stats in save file
    # IB - imprinting bonus (when bred) - must be from dino stats in save file
    # TBHM - tamed base health multiplier (lowers only the health stat just after taming for certain species, from values.json)
    # IwM - increase per wild level modifier (1.0 for official servers)
    # TmM - multiplicative taming-bonus modifier PerLevelStatsMultiplier_DinoTamed_Affinity
    # IdM - increase per domestic level modifier PerLevelStatsMultiplier_DinoTamed
    # TaM - additive taming-bonus modifier PerLevelStatsMultiplier_DinoTamed_Add
    # IBM - Baby imprinting stats scale multiplier (global variable usually 1)
    #
    # Formula

    # V = (B * ( 1 + Lw * Iw * IwM) + Ta * TaM) * (1 + TE * Tm * TmM) * (1 + Ld * Id * IdM)
    #          (           a      )  (   b    )   (          c      )   (          d      )
    # e = ((B * a) + b) 
    # V = e * c * d


    foodStatValues = valuesjson_entry['fullStatsRaw'][INDEX_FOOD]
    B = foodStatValues[0]
    Lw = food_levelups_wild
    Ld = food_levelups_tame
    Iw = foodStatValues[1]
    Id = foodStatValues[2]
    Ta = foodStatValues[3]
    Tm = foodStatValues[4]
    TIE = getPropertyValueByName(statusComponent['properties'], 'TamedIneffectivenessModifier') 
    if not TIE:
        TIE = 0.0
    TE = 1 / (1 + TIE)

    IB = getPropertyValueByName(statusComponent['properties'], 'DinoImprintingQuality') 
    if not IB:
        IB = 0.0

    TBHM = valuesjson_entry['TamedBaseHealthMultiplier'] # we actually don't care.
    IwM = 1.0 ## Server config

### DEBUG ###
    name = getPropertyValueByName(dino['properties'], 'TamedName')
    print("{} - B {}  Lw {}  Ld {}  Iw {}  Id {}  Ta {}  Tm {}  TE {}  IB {}".format(name, B, Lw, Ld, Iw, Id, Ta, Tm, TE, IB))
### DEBUG ###

    TmM = 1.0 # PerLevelStatsMultiplier_DinoTamed_Affinity from Game.ini
    IdM = 1.0 # PerLevelStatsMultiplier_DinoTamed from Game.ini
    TaM = 1.0 # PerLevelStatsMultiplier_DinoTamed_Add from Game.ini
    IBM = 1.0 ## Server config

    return calculate_stat_value(Lw=Lw, Iw=Iw, IwM=IwM, IB=IB, Ta=Ta, TaM=TaM, TE=TE, Tm=Tm, TmM=TmM, Ld=Ld, Id=Id, IdM=IdM, B=B, IBM=IBM, TBHM=1.0)


# V = (B × ( 1 + Lw × Iw × IwM) × TBHM × (1 + IB × 0.2 × IBM) + Ta × TaM) × (1 + TE × Tm × TmM) × (1 + Ld × Id × IdM)
#          (       a          )          (       b          )               (         c       )   (         d       )
#                                        
#      (B * a * TBHM * b + (Ta * TaM)) * c * d
def calculate_stat_value(*, Lw, Iw, IwM, IB, Ta, TaM, TE, Tm, TmM, Ld, Id, IdM, B, IBM, TBHM):
    a = (1.0 + (Lw * Iw * IwM))
    b = (1.0 + (IB * 0.2 * IBM))
    c = (1.0 + (TE * Tm * TmM))
    d = (1.0 + (Ld * Id * IdM))
    V = ((B * a * TBHM * b) + (Ta * TaM)) * c * d
    return V


def report_hungry_tames(hungry_tames_filename):
    values_by_bp = load_values_json()

    with open(hungry_tames_filename, "w") as outfile:
        # We're denormalizing here; producing a flat list out of hierarchical objects.
        header = "ID\tDino\tLevel\tDino Name\tx\ty\tz\tFood Levelups Wild\tFood Levelups Tame\tFood Current\tFood Total\tFoodPercent\tTamerString\tPlayerName\tTribeName\n"
        outfile.write(header)

        for dino_id in tame_dinos:
            dino = tame_dinos[dino_id]
            if dino['class'] in not_really_dinos:
                continue  # skip rafts and stuff
            isInCryopod = False
            for name in dino['names']:
                if "PrimalItem_WeaponEmptyCryopod" in name:
                    isInCryopod = True
            if isInCryopod:
                continue # skip cryopods

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

            food_total = calculate_food_total(dino, values_by_bp.get(dino['class'], None), base_character_level, extra_character_level, food_levelups_wild, food_levelups_tame)
            if (food_total < 1):
                food_percent = 0
                print("Warning - could not calculate food total for class {}".format(dino['class']))
            else:
                food_percent = food_current_value / food_total


            row = str(dino['id']) + \
                "\t" + str(simplifyName(dino['class'])) + \
                "\t" + str(base_character_level + extra_character_level) + \
                "\t" + str(getPropertyValueByName(dino['properties'], 'TamedName')) + \
                "\t" + str(dino['location']['x']) + \
                "\t" + str(dino['location']['y']) + \
                "\t" + str(dino['location']['z']) + \
                "\t" + str(food_levelups_wild) + \
                "\t" + str(food_levelups_tame) + \
                "\t" + str(food_current_value) + \
                "\t" + str(food_total) + \
                "\t" + str(food_percent) + \
                "\t" + str(getPropertyValueByName(dino['properties'], 'TamerString')) + \
                "\t" + str(getPropertyValueByName(dino['properties'], 'OwningPlayerName')) + \
                "\t" + str(getPropertyValueByName(dino['properties'], 'TribeName'))
            if (food_percent < 0.50):
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
    #convert_binary_to_json(ark_binary_filename, json_full_filename)
    iprint("1/5 Wrote {}\n".format(json_full_filename))

    iprint("2/5 Simplifying json so we can read the game objects...")
    #simplify_json_to_game_objects(json_full_filename, json_objects_filename)
    iprint("2/5 Wrote {}\n".format(json_objects_filename))

    iprint("3/5 Processing game objects. This takes the longest time; several minutes...")
    process_game_objects(json_objects_filename) # purely in-memory

    iprint("4/5 Reporting inventories...")
    #report_inventories(inventory_filename)
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

