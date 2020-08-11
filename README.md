# Convert Ark files to JSON and Analyze Game Objects

## Purpose

This set of scripts can convert Ark save files (from July 2020)
to json and then extract certain game object lists 
from that into a tab-delimited text file (basically csv).

Right now, it's focused on inventories (things that can contain
items, and the items within them).  This helps server admins
locate special items and generally keep track of what's up.

A future addition will list hungry dinos (list of tame dinos on 
the map and their food status), which can help identify tames that
have wandered away from their feeding trough or otherwise 
are missing out on food.

## Installation

The conversion from a binary MapName.ark file to json relies
on a C# executable for Windows.  This is a self-contained
binary with no installer and no DLLs.  The python script
will call it automatically provided it's in the same directory
as the python script.

To use the python script, you need to install its dependencies.
For now, it only has one external dependency: naya.  You can
get this with "pip install naya", although if you want to
use conda or virtualenv first to isolate your install, that 
should be fine.

    pip install naya
    mkdir ark
    copy ArkBinaryToJsonConvertor.exe ark
    copy ConvertAndAnalyzeArkSave.py ark
    copy MyMap.ark ark
    cd ark


## Usage Summary

To run:

    python ConvertAndAnalyzeArkSave.py MyMap.ark

You should see output like this:

    $ python ConvertAndAnalyzeArkSave.py TheIsland.ark

    1/4 Converting TheIsland.ark from binary to json; this takes a minute...
        Starting conversion from Ark binary to json.  First argument is Ark save file path; second is json file path.
        Finished reading save file and writing json. Got 188237 objects total.
    1/4 Wrote TheIsland.json

    2/4 Simplifying json so we can read the game objects...
    2/4 Wrote TheIsland_game_objects.json

    3/4 Processing game objects. This takes the longest time; several minutes...
    4/4 Reporting inventories...
    4/4 Wrote TheIsland_inventory.txt

    Complete.

This will produce the files:

    MyMap.json
    MyMap_game_objects.json
    MyMap_inventory.txt

You probably want to read the inventory txt file with Excel or somesuch.
It can be treated as tab-delimited csv (rename it to .tab if you want
Excel to just magically understand it).  It's a very wide file, so 
although you can read it in any plain text viewer, do make your
window wide so it doesn't line wrap.

## Bug Reports

Yeah, there are probably bugs.  I didn't write the binary to json 
conversion library; I just hooked it up into a statically linked exe
for ease of use.  I actually don't really know C# and can't do
much with it if it breaks.  You can take a look and submit a
pull request though.

The python script is stuff I wrote and can reasonably fix.  That
said, this isn't a huge priority for me.  You'll probably get
farther by submitting a pull request with a fix than if you ask me.
It was mostly created as a one-off for a friend's need, and I'm 
publishing it up to github in case anyone finds it helpful.

I am unlikely to keep up with updates to the Ark server file format
over time.  Don't rely on this.

## Dependencies and Inspiration

The C# format conversion exe used copy-paste code examples from 
http://github.com/cadon/ARKStatsExtractor/blob/dev/ARKBreedingStats/ARKBreedingStats.csproj
to handle read from binary and write to json (with some adjustments
to make the code actually handle everything, not just dino stats).
My source code is at https://github.com/jennybrown8/ArkGameConvertBinaryToJson
if you wanted to build it yourself.

The C# code uses a library called ARKSaveGameToolkit, to
do all of the heavy lifting.  The Java version is out of
date and unlikely to be updated; the C# version is a rewrite
and seems to be up to date as of July 2020 (it's working great).
I downloaded their source and built the DLLs for my use from that.
https://github.com/Flachdachs/ArkSavegameToolkit

The python code is entirely from scratch.  It uses naya for streaming
json processing of the game objects array; that knows nothing
of Ark, and just knows how to handle json.  

The processing in my python code is definitely sensitive 
to the exact json format (both whitespace and certain 
json object names), so it'll break if the format changes.


