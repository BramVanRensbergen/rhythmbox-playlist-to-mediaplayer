#! /usr/bin/env python

# Author: Bram Van Rensbergen
# Based on Kyle Dickerson's Rhythmbox-Playlists-Export (https://github.com/kdickerson/Rhythmbox-Playlists-Export)
# email: mail@bramvanrensbergen.com
# Source: https://github.com/BramVanRensbergen/Rhythmbox-Playlists-To-MediaPlayer
#
# to run: 
# python /home/decius/Dropbox/apps/programs/rhythmbox-playlist-to-mediaplayer/rhythmbox-playlists-export.py

# To use with a device mounted using gvfs (e.g. Android), set a local TARGET_DIR, and set the device's mount path at EXTERNAL_RSYNC_DIR; the local directory will be synced with the device using rsync
# (because gvfs does not allow 'touch', and is generally a PITA to work with)

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
logging.basicConfig(level=logging.DEBUG) 

PRESET = 'Android'
#PRESET = 'CarPlaylist'
#PRESET = 'CarCD'

CONVERT_FLAC_TO_MP3 = True  #True: convert all flac files to mp3; requires 'sox' to be installed'; False: flac files are handled just like mp3 files

REMOVE_OLD_FILES = True #True: all files not just synced are deleted from TARGET_DIR. Use with caution!


#The following are overwritten by PRESET values

# location on current station where files are stored
TARGET_DIR = None 

# Directory in TARGET_DIR and where music files are stored.
# Set to '' to store in TARGET_DIR itself.
MUSIC_DIR = None 

# Directory in TARGET_DIR where playlists files are stored
# if left at none, playlist files are not synchronized
PLAYLIST_DIR = None 

#True: a folder is created for the files of each of the playlists indicated above
#False: no subfolder is created per playlist.  If  MAINTAIN_SOURCE_DIR_STRUCTURE == False, this means all files end up in one big directory. 
EACH_PLAYLIST_IN_SEPARATE_DIR = None
    
#True: keep the directory structure of the source media, e.g. maintain (sub)folders
MAINTAIN_SOURCE_DIR_STRUCTURE = None

#If this is set, after RB playlists are synced to TARGET_DIR, rsync is used to sync TARGET_DIR with EXTERNAL_RSYNC_DIR (following the same folder structure, so music files are placed in EXTERNAL_RSYNC_DIR/MUSIC_DIR)
# you can set this directly, or use the get_gvfs_mount_path function
EXTERNAL_RSYNC_DIR = None
EXTERNAL_RSYNC_DIR_LOOKUP = False; #True: lookup on runtime with get_gvfs_mount_path function (make sure to set the id for your device in that function)

if PRESET == 'Android':
    TARGET_DIR = '/media/local/MusicCopy/Android/' #'/run/user/1000/gvfs/mtp:host=%5Busb%3A001%2C010%5D/Internal storage/'
    MUSIC_DIR = 'Music/'
    PLAYLIST_DIR = 'Playlists/'
    SKIP_PLAYLISTS = ['Recently Added', 'Recently Played', 'Top', 'check', 'ncd', 'nu'] #Skip these playlists
    SYNC_PLAYLISTS = ['latin party', 'classic rock', 'party', 'sets', 'chill', 'lounge', 'dubstep'] #ONLY sync these playlists; if this is empty, sync ALL playlists except those in skip_playlists
    EACH_PLAYLIST_IN_SEPARATE_DIR = False 
    MAINTAIN_SOURCE_DIR_STRUCTURE = True 
    EXTERNAL_RSYNC_DIR_LOOKUP = True

if PRESET == 'CarPlaylist':
    TARGET_DIR = '/media/local/MusicCopy/Car/Playlist/'   #'/run/media/decius/MUZIEK/Playlist'
    MUSIC_DIR = '' # keep in base dir
    PLAYLIST_DIR = None # dont sync
    SKIP_PLAYLISTS = ['soundtrack', 'Recently Added', 'Recently Played', 'Top', 'check', 'ncd', 'nu', 'cd', 'progressive', 'margi', 'classical', 'varia'] #Skip these playlists
    SYNC_PLAYLISTS = [] #ONLY sync these playlists; if this is empty, sync ALL playlists except those in skip_playlists
    EACH_PLAYLIST_IN_SEPARATE_DIR = True
    MAINTAIN_SOURCE_DIR_STRUCTURE = False
    
if PRESET == 'CarCD':
    TARGET_DIR = '/media/local/MusicCopy/Car/CD/'    #'/run/media/decius/MUZIEK/CD'
    MUSIC_DIR = '' # keep in base dir
    PLAYLIST_DIR = None # dont sync
    SKIP_PLAYLISTS = ['Recently Added', 'Recently Played', 'Top', 'check', 'ncd', 'nu'] #Skip these playlists
    SYNC_PLAYLISTS = ['cd'] #ONLY sync these playlists; if this is empty, sync ALL playlists except those in skip_playlists
    EACH_PLAYLIST_IN_SEPARATE_DIR = False
    MAINTAIN_SOURCE_DIR_STRUCTURE = True


PLAYLIST_FORMAT = 'M3U' # only M3U currently supported, See note about Rhythmbox URI encoding above which also pertains to PLS support
RHYTHMBOX_STARTUP_WAIT = 1 #15 seconds, if Rhythmbox hasn't finished initializing the exports won't work (haven't found a programmatic way to check this)
global temporary_playlist_dir # we'll export RB playlists to this temporary dir
temporary_playlist_dir = None

def rhythmbox_playlist_export():   
    scriptStart = time.time()
    
    global temporary_playlist_dir    
    temporary_playlist_dir = subprocess.getoutput('mktemp -d')
    logging.info('Created temp directory to store playlist files at %s' % temporary_playlist_dir)    
    
    if not os.path.exists(TARGET_DIR + MUSIC_DIR):
        logging.info("Creating directory for destination media")
        os.makedirs(TARGET_DIR + MUSIC_DIR)
    
    if PLAYLIST_DIR is not None and not os.path.exists(TARGET_DIR + PLAYLIST_DIR):
        logging.info("Creating directory for local playlists")
        os.makedirs(TARGET_DIR + PLAYLIST_DIR)
    

    #export rhythmbox playlists  
    subprocess.call('rhythmbox-client --no-present', shell=True)
    logging.info('Pausing %d seconds for Rhythmbox initialization' % (RHYTHMBOX_STARTUP_WAIT))
    time.sleep(RHYTHMBOX_STARTUP_WAIT) # rhythmbox isn't ready until shortly after rhythmbox-client returns
    export_playlists()
        
    #copy all files in those playlists to destination dir, and export edited version of the playlists refering to the new source    
    sync_playlist_media()
    
    run_external_rsync_if_needed()
   
    #cleanup    
    if REMOVE_OLD_FILES:
        logging.info("Removing all files in %s with last modified date before start of the script" % TARGET_DIR)
        
        for root, subdirs, files in os.walk(TARGET_DIR):
                for file in files:
                    fullpath = os.path.join(root,file)
                    if os.stat(fullpath).st_mtime < scriptStart:
                        run_cmd('rm \"%s\"' % fullpath)    
        
        
    
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
    
    #check whether we have to sync this playlist!
    sync_this = True
    if len(SYNC_PLAYLISTS) > 0 and not playlist_name in SYNC_PLAYLISTS: 
        sync_this = False #working with whitelist, and this playlist is not on it
   
    if playlist_name in SKIP_PLAYLISTS: 
        sync_this = False #playlist is on blacklist, skip it
    
    if not sync_this:
        logging.debug('Skipping %s' %playlist_name)
        continue
    
    #Try to export the playlist
    filename = "%s.%s" % (re.sub(clean_names_regex, '_', playlist_name), PLAYLIST_FORMAT.lower())
    logging.info("Exporting '%s' to '%s'" % (playlist_name, filename))
    try:
        fileURI = 'file://%s/%s' % (temporary_playlist_dir, filename)
        logging.debug("URI: %s" % (fileURI))
        playlist_manager.ExportPlaylist(playlist_name, fileURI, asM3U, dbus_interface='org.gnome.Rhythmbox3.PlaylistManager')
    except dbus.exceptions.DBusException as ex:
        logging.error("Failed to export playlist: %s" % (playlist_name))
        if ex.get_dbus_name().find('Error.NoReply') > -1:
            logging.error("Perhaps it was empty?  Attempting to restart Rhythmbox...")
            subprocess.call('rhythmbox-client --no-present')
            logging.info('Pausing %d seconds for Rhythmbox initialization' % (RHYTHMBOX_STARTUP_WAIT))
            time.sleep(RHYTHMBOX_STARTUP_WAIT) # rhythmbox isn't ready until shortly after rhythmbox-client returns
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
        playlist_line_base = '../' + MUSIC_DIR + playlist_name + '/'
        destination_base = '%s%s/' % (TARGET_DIR + MUSIC_DIR, playlist_name) 
        
        if not os.path.exists(destination_base):
            logging.info("Creating folder for playlist %s" % (playlist_name))
            os.makedirs(destination_base)
    else:
        playlist_line_base = '../' + MUSIC_DIR
        destination_base = TARGET_DIR + MUSIC_DIR
    
    if MAINTAIN_SOURCE_DIR_STRUCTURE:
        # find common path between all files in this playlist
        # we use this to main the directory structure (we don't maintain the entire tree, only the part not common between all files)
        paths = []
        for line in playlist_text:
            if not line.startswith('#'):
                paths.append(line)
        prefix = path.dirname(path.commonprefix(paths)) + os.sep
        #logging.info('prefix: %s' % (prefix))
    
    for line in playlist_text:
        if line.startswith('#'):
            playlist_text_out.append(line) #copy comment lines as is
            continue
        source_path = line.rstrip('\n')      
        fname = path_leaf(source_path)
        
        if MAINTAIN_SOURCE_DIR_STRUCTURE:
            destination_subdirs = source_path.replace(prefix, '').replace(fname, '')
            logging.info(destination_subdirs)
            destination_path = destination_base + destination_subdirs;
            if not os.path.exists(destination_path):
                logging.info("Creating folder(s) %s" % (destination_subdirs))
                os.makedirs(destination_path)
            playlist_line_prefix = playlist_line_base + destination_subdirs
        else:
            destination_path = destination_base
            playlist_line_prefix = playlist_line_base
        
        touch_existing = False; #if target file already exists, we'll touch it so we can keep track of what files are synced in this run, so we can remove any older files if needed
        
        
        if CONVERT_FLAC_TO_MP3 and fname.endswith('.flac'): # file is flac, and we should convert it to mp3 
            fname = fname.replace('.flac', '.mp3')
            
            if not os.path.isfile(destination_path + fname.replace('.flac', '.mp3')):  
                run_cmd('sox \"%s\" \"%s\"' % (source_path, destination_path + fname)) #use sox to convert the source flac, and save it as mp3 to destionation dir
            else:
                touch_existing = True
                
        else: # file is not flac i.e. likely mp3   
            if not os.path.isfile(destination_path + fname):
                run_cmd('cp \"%s\" \"%s\"' % (source_path, destination_path)) #copy file to destination!
            else:
                touch_existing = True
        
        if touch_existing:
            run_cmd('touch \"%s\"' % (destination_path + fname)) # touch existing file, so we know we should keep it
        
        #add path to new playlist
        playlist_text_out.append(playlist_line_prefix + fname + '\n') 
              
     #save playlist file
    if PLAYLIST_DIR is not None:
        playlist_out = open("%s/%s" % (TARGET_DIR + PLAYLIST_DIR, filename[filename.rfind('/')+1:]), 'w')
        playlist_out.writelines(playlist_text_out)
        playlist_out.close()

#run the indicated shell command
def run_cmd(cmd):
    logging.debug('Executing: %s' % (cmd))
    subprocess.call(cmd, shell=True)
   

#return the last part of a path (generally, the filename)
def path_leaf(path):
    head, tail = ntpath.split(path)
    return tail or ntpath.basename(head)

def run_external_rsync_if_needed():    
    global EXTERNAL_RSYNC_DIR
    
    if EXTERNAL_RSYNC_DIR_LOOKUP:
        EXTERNAL_RSYNC_DIR = get_gvfs_mount_path()
   
   
    if EXTERNAL_RSYNC_DIR is not None:
        logging.info('Will now sync %s with %s' % (TARGET_DIR, EXTERNAL_RSYNC_DIR))
        
        if not os.path.exists(EXTERNAL_RSYNC_DIR):
            logging.warn("target folder is not mounted: %s" % (EXTERNAL_RSYNC_DIR))
            return
     
        if not os.path.exists(EXTERNAL_RSYNC_DIR + MUSIC_DIR):
            logging.warn("Music directory does not exist on target: %s" % (EXTERNAL_RSYNC_DIR + MUSIC_DIR))
            return
        
        #sync music folder
        cmd = 'rsync -avhO --no-times --no-perms --delete --ignore-existing \"%s\" \"%s\"' % (TARGET_DIR + MUSIC_DIR, EXTERNAL_RSYNC_DIR + MUSIC_DIR)
        run_cmd(cmd)
        
        
        if PLAYLIST_DIR is not None: 
            if not os.path.exists(EXTERNAL_RSYNC_DIR + PLAYLIST_DIR):
                logging.info("Creating directory for target playlists at %s " % (EXTERNAL_RSYNC_DIR + PLAYLIST_DIR))
                os.makedirs(EXTERNAL_RSYNC_DIR + PLAYLIST_DIR)
             
            #sync playlists
            cmd = 'rsync -avhO --no-times --no-perms --delete \"%s\" \"%s\"' % (TARGET_DIR + PLAYLIST_DIR, EXTERNAL_RSYNC_DIR + PLAYLIST_DIR)
            run_cmd(cmd)

# example output: /run/user/1000/gvfs/mtp:host=%5Busb%3A001%2C010%5D/Internal storage/
def get_gvfs_mount_path():
    id = "2a70:f003" #device id, find using lsusb
    
    device_info = subprocess.getoutput("lsusb -d %s | sed 's/:.*//'" % id).split()    
    bus = device_info[1]
    device = device_info[3]
    uid = subprocess.getoutput('id -u $USER')
    
    path = '/run/user/' + uid + '/gvfs/mtp:host=%5Busb%3A' + bus + '%2C' + device +'%5D/Internal storage/'
    logging.debug('obtained gvfs mount path: %s' %path )
    return path

rhythmbox_playlist_export()

