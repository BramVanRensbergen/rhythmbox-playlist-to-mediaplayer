Rhythmbox-Playlists-To-MediaPlayer
==========================
Author: Bram Van Rensbergen <mail@bramvanrensbergen.com>

A tool to export rhythmbox playlists and their songs. 
You select a number of playlists; all songs in these playlist are copied, and the playlists are duplicated, modified to refer to the new files, and copied as well.

Primary goal: to sync part of your audio library to an external media player (cell phone, rockbox ipod, ...).

This tool is based on Kyle Dickerson's <a href = "https://github.com/kdickerson/Rhythmbox-Playlists-Export">Rhythmbox-Playlists-Export</a>, 
which can be used to sync an entire media library to a different computer (using ssh). I repurposed his code to sync part of a media library (only files contained in the playlists
you are syncing) to a local folder (likely a mounted cell phone or other media player).

You will need to configure the file before use, generally just to indicate destination folders and which playlists to sync.

The tool was only tested on linux, but in theory should work on any OS. 

Known issues:
* All files are placed in a single folder, so all songs should have unique filenames; when there are multiple songs with the same filename, only one is used.