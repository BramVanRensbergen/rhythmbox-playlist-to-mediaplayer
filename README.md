Rhythmbox-Playlist-To-MediaPlayer
==========================
Author: Bram Van Rensbergen <mail@bramvanrensbergen.com>

A tool to export rhythmbox playlists and their songs. 
You select a number of playlists; all songs in these playlist are copied, and the playlists are duplicated, modified to refer to the new files, and copied as well.

Primary goal: to sync part of your audio library to an external media player (cell phone, rockbox ipod, ...), either mounted locally or over ssh.

I created this for personal use, but anyone is free to use it. You will need to configure the file before use, such as to indicate destination folders and which playlists to sync.

This tool is based on Kyle Dickerson's <a href = "https://github.com/kdickerson/Rhythmbox-Playlists-Export">Rhythmbox-Playlists-Export</a>, 
which is intended to sync an entire media library to a different computer (using ssh). I repurposed his code to sync part of a media library (only files contained in the playlists
you are syncing) to a local folder (likely a connected cell phone or other media player).

The tool is designed for Linux and requires python3 (and optionally sox, if you wish to export flac files as mp3). 


When syncing a gvfs-mounted device (e.g., Android), use of the script is somewhat more complicated, (because gvfs-mounted filesystems do not allow the 'touch' command, which is used to keep track of which files were just synced, so that, if the option is enabled, any other music files can be removed). Instructions:
	- make sure rsync is installed
    - mount your device with gvfs (for Android, make sure to toggle the option 'Transfer files' on your device, then mount the filesystem e.g. through Nautilus)
    - set a local TARGET_DIR (i.e. on your pc, not on your device) in the configuration file
    - optional: if you have more than one gvfs device mounted, set the path to the device you wish to sync under EXTERNAL_RSYNC_DIR    
    - your music will first be exported to the local directory, then synced with rsync with your device
