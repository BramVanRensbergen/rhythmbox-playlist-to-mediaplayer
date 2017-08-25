#! /usr/bin/env python

# Author: Bram Van Rensbergen
# Based on Kyle Dickerson's Rhythmbox-Playlists-Export (https://github.com/kdickerson/Rhythmbox-Playlists-Export)
# email: mail@bramvanrensbergen.com
# Source: https://github.com/BramVanRensbergen/Rhythmbox-Playlists-To-MediaPlayer
#
# to run: 
# python /home/decius/Dropbox/apps/programs/rhythmbox-playlist-to-mediaplayer/rhythmbox-playlists-export.py




import dbus
import os
import glob
import re
import urllib
import time
import ntpath
from xml.etree.ElementTree import Element, ElementTree
from os import path
import subprocess
import logging
from test.test_dbm_dumb import _fname
logging.basicConfig(level=logging.DEBUG) 

# rather than changing all user options separately, you may switch to a preset which contains a set of default values for some of these variables
PRESET = 'Android'	# Android CarPlaylist CarCD

CONVERT_FLAC_TO_MP3 = True	# True: convert all flac files to mp3; requires 'sox' to be installed'; False: flac files are handled just like mp3 files

REMOVE_OLD_FILES = True	# True: all files not just synced are deleted from TARGET_DIR, and empty directories are removed. Use with caution!

# location on current station where files are stored
TARGET_DIR = None 

# Directory in TARGET_DIR and where music files are stored.
# Set to '' to store in TARGET_DIR itself.
MUSIC_DIR = None 

# Directory in TARGET_DIR where playlists files are stored
# if left at none, playlist files are not synchronized
PLAYLIST_DIR = None 

# True: keep the directory structure of the source media, e.g. maintain (sub)folders
# Usually either this is true and EACH_PLAYLIST_IN_SEPARATE_DIR is false, or the other way around (these are the only scenarios that were tested)
MAINTAIN_SOURCE_DIR_STRUCTURE = None

# True: a folder is created for the files of each of the playlists indicated above (this means duplicates will be created for files that exist in multiple exported playlists)
# False: no subfolder is created per playlist.	If	MAINTAIN_SOURCE_DIR_STRUCTURE == False, this means all files end up in one big directory. 
# Usually either this is true and MAINTAIN_SOURCE_DIR_STRUCTURE is false, or the other way around (these are the only scenarios that were tested)
EACH_PLAYLIST_IN_SEPARATE_DIR = None
RENAME_BASED_ON_INDEX_IN_PLAYLIST = True # True: prefix all files based with their index in their playlist. Only used (because only plausible) if EACH_PLAYLIST_IN_SEPARATE_DIR is true
	

# If this is set, after RB playlists are synced to TARGET_DIR, rsync is used to sync TARGET_DIR with EXTERNAL_RSYNC_DIR (following the same folder structure, so music files are placed in EXTERNAL_RSYNC_DIR/MUSIC_DIR)
# You can rsync to any locally mounted folder, or over ssh (just edit RSYNC_COMMAND) 
# when using ssh, make sure MUSIC_DIR and	PLAYLIST_DIR already exist in EXTERNAL_RSYNC_DIR
SYNC_TARGET_TO_RSYNC = False

RSYNC_COMMAND = "rsync --verbose --progress --delete --omit-dir-times --no-perms --recursive --inplace --size-only -e \"ssh -p 2222\" %s %s decius@192.168.2.26:%s"	
# first '%s' will be replaced with TARGET_DIR + MUSIC_DIR, second one with TARGET_DIR + PLAYLIST_DIR, final one with EXTERNAL_RSYNC_DIR

# If SYNC_TARGET_TO_RSYNC is true, TARGET_DIR will be synced to this folder 
# You can set this directly, or, if you have mounted a single device using gvfs, look up the path at runtime
EXTERNAL_RSYNC_DIR = None	# example: /run/user/1000/gvfs/mtp:host=%5Busb%3A001%2C010%5D/Internal storage/
EXTERNAL_RSYNC_DIR_GVFS_LOOKUP = False	# True: lookup EXTERNAL_RSYNC_DIR on runtime with get_gvfs_mount_path function. Use to rsync to a device mounted as mtp (e.g., Android)

if PRESET == 'Android':
	SYNC_TARGET_TO_RSYNC = True
	EXTERNAL_RSYNC_DIR = '/data/data/com.arachnoid.sshelper/home/SDCard/'
	TARGET_DIR = '/media/Alexis/Data/Backup/AndroidMusicCopy/'	# '/media/local/MusicCopy/Android/'
	MUSIC_DIR = 'Music/'
	PLAYLIST_DIR = 'Playlists/'
	SKIP_PLAYLISTS = ['Recently Added', 'Recently Played', 'Top', 'check', 'ncd', 'nu']	# Skip these playlists
	SYNC_PLAYLISTS = ['latin party', 'classic rock', 'party', 'sets', 'chill', 'lounge', 'dubstep', 'relaxation']	# ONLY sync these playlists; if this is empty, sync ALL playlists except those in skip_playlists
	EACH_PLAYLIST_IN_SEPARATE_DIR = False 
	MAINTAIN_SOURCE_DIR_STRUCTURE = True 
	

if PRESET == 'CarPlaylist':
	TARGET_DIR = '/run/media/decius/MUZIEK/Playlist/'
	MUSIC_DIR = ''	# keep in base dir
	PLAYLIST_DIR = None	# dont sync
	SKIP_PLAYLISTS = []	# Skip these playlists
	SYNC_PLAYLISTS = ['classic rock', 'alt rock', 'chill', 'dubstep', 'electro', 'latin', 'latin party', 'lounge', 'metal', 'oldie', 'party', 'punk', 'sets']	# ONLY sync these playlists; if this is empty, sync ALL playlists except those in skip_playlists
	EACH_PLAYLIST_IN_SEPARATE_DIR = True
	MAINTAIN_SOURCE_DIR_STRUCTURE = False
	
if PRESET == 'CarCD':
	TARGET_DIR = '/run/media/decius/MUZIEK/CD/'
	MUSIC_DIR = ''	# keep in base dir
	PLAYLIST_DIR = None	# dont sync
	SKIP_PLAYLISTS = []	# Skip these playlists
	SYNC_PLAYLISTS = ['cd']	# ONLY sync these playlists; if this is empty, sync ALL playlists except those in skip_playlists
	EACH_PLAYLIST_IN_SEPARATE_DIR = False
	MAINTAIN_SOURCE_DIR_STRUCTURE = True


PLAYLIST_FORMAT = 'M3U'	# only M3U currently supported, See note about Rhythmbox URI encoding above which also pertains to PLS support
RHYTHMBOX_STARTUP_WAIT = 1	# 15 seconds, if Rhythmbox hasn't finished initializing the exports won't work (haven't found a programmatic way to check this)
global temporary_playlist_dir	# we'll export RB playlists to this temporary dir
temporary_playlist_dir = None


def rhythmbox_playlist_export():	
	scriptStart = time.time()
	
	global temporary_playlist_dir	
	temporary_playlist_dir = subprocess.getoutput('mktemp -d')
	logging.info('Created temp directory to store playlist files at %s' % temporary_playlist_dir)	
	
	if not os.path.exists(os.path.join(TARGET_DIR, MUSIC_DIR)):
		logging.info("Creating directory for destination media")
		os.makedirs(os.path.join(TARGET_DIR, MUSIC_DIR))
	
	if PLAYLIST_DIR is not None and not os.path.exists(os.path.join(TARGET_DIR, PLAYLIST_DIR)):
		logging.info("Creating directory for local playlists")
		os.makedirs(os.path.join(TARGET_DIR, PLAYLIST_DIR))
	

	# export rhythmbox playlists	
	subprocess.call('rhythmbox-client --no-present', shell=True)
	logging.info('Pausing %d seconds for Rhythmbox initialization' % (RHYTHMBOX_STARTUP_WAIT))
	time.sleep(RHYTHMBOX_STARTUP_WAIT)	# rhythmbox isn't ready until shortly after rhythmbox-client returns
	export_playlists()
		
	# copy all files in those playlists to destination dir, and export edited version of the playlists refering to the new source	
	sync_playlist_media()
			
	if REMOVE_OLD_FILES:
		logging.info("Removing all files in %s with last modified date before start of the script as well as all empty directories" % TARGET_DIR)
		
		for root, subdirs, files in os.walk(TARGET_DIR):
			for file in files:
				fullpath = os.path.join(root, file)
				if os.stat(fullpath).st_mtime + 300 < scriptStart: # +5min, just to be safe
					run_cmd('rm \"%s\"' % fullpath)	
			for subdir in subdirs:
				fullpath = os.path.join(root, subdir)
				if len(os.listdir(fullpath)) == 0:					
					run_cmd('rm -d \"%s\"' % fullpath)
		
	run_external_rsync_if_needed()

			
	if temporary_playlist_dir is not None:
		logging.info("Removing temporary playlist directory")
		run_cmd('rm -rf %s' % (temporary_playlist_dir))
	
# export playlist files from Rhythmbox3 to the temporary playlist dir
def export_playlists():	
	logging.info("Exporting playlists...")
	clean_names_regex = re.compile(r'[^\w\s]')
	session_bus = dbus.SessionBus()
	playlist_manager = session_bus.get_object('org.gnome.Rhythmbox3', '/org/gnome/Rhythmbox3/PlaylistManager')
	asM3U = (PLAYLIST_FORMAT == 'M3U')
		
	for playlist_name in playlist_manager.GetPlaylists(dbus_interface='org.gnome.Rhythmbox3.PlaylistManager'):			
		sync_this = True # check whether we have to sync this playlist!
		if len(SYNC_PLAYLISTS) > 0 and not playlist_name in SYNC_PLAYLISTS: 
			sync_this = False	# working with whitelist, and this playlist is not on it
		
		if playlist_name in SKIP_PLAYLISTS: 
			sync_this = False	# playlist is on blacklist, skip it
		
		if not sync_this:
			logging.debug('Skipping %s' % playlist_name)
			continue
		
		# Try to export the playlist
		filename = "%s.%s" % (re.sub(clean_names_regex, '_', playlist_name), PLAYLIST_FORMAT.lower())
		logging.info("Exporting '%s' to '%s'" % (playlist_name, filename))
		try:
			fileURI = 'file://%s' % (os.path.join(temporary_playlist_dir, filename))
				
			playlist_manager.ExportPlaylist(playlist_name, fileURI, asM3U, dbus_interface='org.gnome.Rhythmbox3.PlaylistManager')
		except dbus.exceptions.DBusException as ex:
			logging.error("Failed to export playlist: %s" % (playlist_name))
			if ex.get_dbus_name().find('Error.NoReply') > -1:
				logging.error("Perhaps it was empty?	Attempting to restart Rhythmbox...")
				subprocess.call('rhythmbox-client --no-present')
				logging.info('Pausing %d seconds for Rhythmbox initialization' % (RHYTHMBOX_STARTUP_WAIT))
				time.sleep(RHYTHMBOX_STARTUP_WAIT)	# rhythmbox isn't ready until shortly after rhythmbox-client returns
				playlist_manager = session_bus.get_object('org.gnome.Rhythmbox3', '/org/gnome/Rhythmbox3/PlaylistManager')
			else:
				logging.error("%s:%s" % (ex.get_dbus_name(), ex.get_dbus_message()))
				break	

# copy all files in all exported playlists to the target dir, as well as the playlists themselves
def sync_playlist_media():
	logging.info("Syncing playlists and media...")
	for filename in glob.glob("%s/*.%s" % (temporary_playlist_dir, PLAYLIST_FORMAT.lower())):
		playlist = open(filename, 'r')	
		playlist_text = playlist.readlines()
		playlist.close()
		playlist_text_out = []
		playlist_name = os.path.splitext(path_leaf(filename))[0]
			
		if EACH_PLAYLIST_IN_SEPARATE_DIR:		
			playlist_line_base = '../' + os.path.join(MUSIC_DIR, playlist_name) + '/'
			destination_base = '%s%s/' % (os.path.join(TARGET_DIR, MUSIC_DIR), playlist_name) 
			
			if not os.path.exists(destination_base):
				logging.info("Creating folder for playlist %s" % (playlist_name))
				os.makedirs(destination_base)
		else:
			playlist_line_base = '../' + MUSIC_DIR
			destination_base = os.path.join(TARGET_DIR, MUSIC_DIR)
		
		if MAINTAIN_SOURCE_DIR_STRUCTURE:
			# find common path between all files in this playlist
			# we use this to main the directory structure (we don't maintain the entire tree, only the part not common between all files)
			paths = []
			for line in playlist_text:
				if not line.startswith('#'):
					paths.append(line)
			prefix = path.dirname(path.commonprefix(paths)) + os.sep
			# logging.info('prefix: %s' % (prefix))
				
		n_songs = int(len(playlist_text) / 2) + 1 # usually one comment line per song
		n_songs_digits = len(str(n_songs)) # used to pre-pad index with zero's
		index_in_playlist = 0
		
		for line in playlist_text:
			if line.startswith('#'):
				playlist_text_out.append(line)	# copy comment lines as is
				continue
			source_absolute_path = line.rstrip('\n')		
			fname = path_leaf(source_absolute_path)
			
			if RENAME_BASED_ON_INDEX_IN_PLAYLIST and EACH_PLAYLIST_IN_SEPARATE_DIR:
				index_in_playlist += 1
				index_prefix = str(index_in_playlist).zfill(n_songs_digits)
				fname = index_prefix + ' ' + fname
			
			if MAINTAIN_SOURCE_DIR_STRUCTURE:
				destination_subdirs = source_absolute_path.replace(prefix, '').replace(fname, '')
				destination_dir = os.path.join(destination_base, destination_subdirs)
				
				if not os.path.exists(destination_dir):
					logging.info("Creating folder(s) %s" % (destination_subdirs))
					os.makedirs(destination_dir)
				playlist_line_prefix = os.path.join(playlist_line_base, destination_subdirs)
				
			else:
				destination_dir = destination_base
				playlist_line_prefix = playlist_line_base
			
			touch_existing = False;	# if target file already exists, we'll touch it so we can keep track of what files are synced in this run, so we can remove any older files if needed
						
			if CONVERT_FLAC_TO_MP3 and fname.endswith('.flac'):	# file is flac, and we should convert it to mp3 
				fname = fname.replace('.flac', '.mp3')
				destination_absolute_path = os.path.join(destination_dir, fname)
				
				if not os.path.isfile(destination_absolute_path):	
					run_cmd('sox \"%s\" \"%s\"' % (source_absolute_path, destination_absolute_path))	# use sox to convert the source flac, and save it as mp3 to destionation dir
				else:
					touch_existing = True
					
			else:	# file is not flac i.e. likely mp3	
				destination_absolute_path = os.path.join(destination_dir, fname)
				
				if not os.path.isfile(destination_absolute_path):
					run_cmd('cp \"%s\" \"%s\"' % (source_absolute_path, destination_absolute_path))	# copy file to destination!
				else:
					touch_existing = True
			
			if touch_existing and REMOVE_OLD_FILES:
				run_cmd('touch \"%s\"' % destination_absolute_path)	# touch existing file, so we know we should keep it
			
			# add path to new playlist
			playlist_text_out.append(os.path.join(playlist_line_prefix, fname) + '\n')
				
		 # save playlist file
		if PLAYLIST_DIR is not None:
			playlist_out = open("%s/%s" % (os.path.join(TARGET_DIR, PLAYLIST_DIR), filename[filename.rfind('/') + 1:]), 'w')
			playlist_out.writelines(playlist_text_out)
			playlist_out.close()

# run the indicated shell command
def run_cmd(cmd):
	logging.debug('Executing: %s' % (cmd))
	subprocess.call(cmd, shell=True)

# return the last part of a path (generally, the filename)
def path_leaf(path):
	head, tail = ntpath.split(path)
	return tail or ntpath.basename(head)


def run_external_rsync_if_needed():	
	global EXTERNAL_RSYNC_DIR
	
	syncingToLocalFilesystem = 'ssh' not in RSYNC_COMMAND # syncing to locally mounted dir or to remote filesystem?
	
	if not SYNC_TARGET_TO_RSYNC:
		return
	
	if EXTERNAL_RSYNC_DIR_GVFS_LOOKUP:
		EXTERNAL_RSYNC_DIR = get_gvfs_mount_path()
	
	logging.info(EXTERNAL_RSYNC_DIR)
				
	if EXTERNAL_RSYNC_DIR is None:
		logging.warn('EXTERNAL_RSYNC_DIR is not set, skipping rsync')
		return
	
	logging.info('Will now rsync %s with %s' % (TARGET_DIR, EXTERNAL_RSYNC_DIR))
			
	if syncingToLocalFilesystem:	
		if not os.path.exists(EXTERNAL_RSYNC_DIR):
			logging.warn("target folder is not mounted: %s" % (EXTERNAL_RSYNC_DIR))
			return
	 
		if not os.path.exists(os.path.join(EXTERNAL_RSYNC_DIR, MUSIC_DIR)):
			logging.warn("Creating music directory at %s" % (os.path.join(EXTERNAL_RSYNC_DIR, MUSIC_DIR)))
			os.makedirs(os.path.join(EXTERNAL_RSYNC_DIR, PLAYLIST_DIR))							
	
	if PLAYLIST_DIR is not None and syncingToLocalFilesystem and not os.path.exists(os.path.join(EXTERNAL_RSYNC_DIR, PLAYLIST_DIR)):
		logging.info("Creating directory for playlists at %s" % (os.path.join(EXTERNAL_RSYNC_DIR, PLAYLIST_DIR)))
		os.makedirs(os.path.join(EXTERNAL_RSYNC_DIR, PLAYLIST_DIR))
		
	# sync both music and playlists folder
	cmd = RSYNC_COMMAND % (os.path.join(TARGET_DIR, MUSIC_DIR).rstrip('/'), os.path.join(TARGET_DIR, PLAYLIST_DIR).rstrip('/'), os.path.join(EXTERNAL_RSYNC_DIR))
	run_cmd(cmd)	

# gvfs devices are mounted under /run/user/$UID/gvfs/
# if only one device is mounted there, return the path to the device, possibly appended with 'Internal storage' or 'Internal shared storage', if these subfolders exist (as is usually the case for Android)
# else, exit the script
# example output: /run/user/1000/gvfs/mtp:host=%5Busb%3A001%2C010%5D/Internal storage/
def get_gvfs_mount_path():
	logging.info('looking up gvfs mount folder...')
	
	named_mount_subfolders = ['Internal storage', 'Internal shared storage']
	
	uid = subprocess.getoutput('id -u $USER')
	
	gvfs_mount_dir = ("/run/user/%s/gvfs/" % uid)
	
	gvfs_mount_paths = subprocess.getoutput("ls %s" % gvfs_mount_dir).split()
	
	if not gvfs_mount_paths:
		logging.info('no mounted gvfs devices found at %s. For Android, make sure to toggle the option \'Transfer files \', and mount the filesystem (e.g., in Nautilus). Exiting...' % gvfs_mount_dir)
		quit()
	
	if len(gvfs_mount_paths) > 1:
		logging.info('found multiple Android devices mounted as gvfs at %s, please disconnect all devices except the one you are trying to sync, or manually set the mount path in the configuration file under EXTERNAL_RSYNC_DIR. Exiting...' % gvfs_mount_dir)
		quit()
	
	path = os.path.join(gvfs_mount_dir, gvfs_mount_paths[0])
	
	for possible_subfolder in named_mount_subfolders:
		new_path = path + os.sep + possible_subfolder
		
		if (os.path.isdir(new_path)):
			path = new_path
	
	logging.debug('using gvfs mount path: %s' % path)
	return path

rhythmbox_playlist_export()
