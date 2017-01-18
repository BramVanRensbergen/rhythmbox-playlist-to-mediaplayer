#! /usr/bin/env python

# Author: Bram Van Rensbergen
# Based on Kyle Dickerson's Rhythmbox-Playlists-Export (https://github.com/kdickerson/Rhythmbox-Playlists-Export)
# email: mail@bramvanrensbergen.com
# Source: https://github.com/BramVanRensbergen/Rhythmbox-Playlists-To-MediaPlayer
# last modified: September, 2014
#
# to run: 
# python2 /home/decius/Dropbox/apps/programs/rhythmbox-playlists-to-mediaplayer/rhythmbox-playlists-export.py

# NOTE: to delete items, remove the LOCAL_BASE_DIR before sync
# TODO: touch existing files and dirs, at the end delete all files and dirs with LMD before program start

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

preset = 'Android'
#preset = 'CarPlaylist'
#preset = 'CarCD'

SYNC_TO_LOCAL_DIR = True #True: update the local dir with RB playlist

SYNC_LOCAL_TO_TARGET = True #True: sync the local dir to target



#The following are overwritten by preset values

# location on current station where files are stored
LOCAL_BASE_DIR = None 

# location on target device where files are stored
TARGET_BASE_DIR = None
 
# Directory, in both LOCAL_BASE_DIR and TARGET_BASE_DIR, where music files are stored
MUSIC_DIR = None 

# Directory, in both LOCAL_BASE_DIR and TARGET_BASE_DIR, where playlists files are stored
# if left at none, playlist files are not synchronized
PLAYLIST_DIR = None 

#True: a folder is created for the files of each of the playlists indicated above
#False: no subfolder is created per playlist.  If  MAINTAIN_SOURCE_DIR_STRUCTURE == False, this means all files end up in one big directory. 
EACH_PLAYLIST_IN_SEPARATE_DIR = None
    
#True: keep the directory structure of the source media, e.g. maintain (sub)folders
MAINTAIN_SOURCE_DIR_STRUCTURE = None

#True: include 
SYNC_PLAYLIST_FILES_TO_TARGET = True




if preset == 'Android':
    LOCAL_BASE_DIR = '/media/local/MusicCopy/Android/'    
    TARGET_BASE_DIR = '/run/user/1000/gvfs/mtp:host=%5Busb%3A001%2C010%5D/Internal storage/'
    MUSIC_DIR = 'Music/'
    PLAYLIST_DIR = 'Playlists/'
    SKIP_PLAYLISTS = ['Recently Added', 'Recently Played', 'Top', 'check', 'ncd', 'nu'] #Skip these playlists
    SYNC_PLAYLISTS = ['latin party', 'classic rock', 'party', 'sets', 'chill', 'lounge', 'dubstep'] #ONLY sync these playlists; if this is empty, sync ALL playlists except those in skip_playlists
    EACH_PLAYLIST_IN_SEPARATE_DIR = False 
    MAINTAIN_SOURCE_DIR_STRUCTURE = True 

if preset == 'CarPlaylist':
    LOCAL_BASE_DIR = '/media/local/MusicCopy/Car/Playlist/'    
    TARGET_BASE_DIR = '/run/media/decius/MUZIEK/Playlist'
    MUSIC_DIR = '' # keep in base dir
    PLAYLIST_DIR = None # dont sync
    SKIP_PLAYLISTS = ['soundtrack', 'Recently Added', 'Recently Played', 'Top', 'check', 'ncd', 'nu', 'cd', 'progressive', 'margi', 'classical', 'varia'] #Skip these playlists
    SYNC_PLAYLISTS = [] #ONLY sync these playlists; if this is empty, sync ALL playlists except those in skip_playlists
    EACH_PLAYLIST_IN_SEPARATE_DIR = True
    MAINTAIN_SOURCE_DIR_STRUCTURE = False
    
if preset == 'CarCD':
    LOCAL_BASE_DIR = '/media/local/MusicCopy/Car/CD/'    
    TARGET_BASE_DIR = '/run/media/decius/MUZIEK/CD'
    MUSIC_DIR = '' # keep in base dir
    PLAYLIST_DIR = None # dont sync
    SKIP_PLAYLISTS = ['Recently Added', 'Recently Played', 'Top', 'check', 'ncd', 'nu'] #Skip these playlists
    SYNC_PLAYLISTS = ['cd'] #ONLY sync these playlists; if this is empty, sync ALL playlists except those in skip_playlists
    EACH_PLAYLIST_IN_SEPARATE_DIR = False
    MAINTAIN_SOURCE_DIR_STRUCTURE = True

#True: convert all flac files to mp3; requires 'sox' to be installed.
#False: flac files are handled just like mp3 files
CONVERT_FLAC_TO_MP3 = True 

PLAYLIST_FORMAT = 'M3U' # only M3U currently supported, See note about Rhythmbox URI encoding above which also pertains to PLS support
temp_playlist_dir = '/home/decius/Desktop/temp'  #playlists are temporarily stored here
rhythmbox_startup_wait = 1 #15 seconds, if Rhythmbox hasn't finished initializing the exports won't work (haven't found a programmatic way to check this)

def rhythmbox_export_playlists_to_local_copy():
    #create folders if necessary
    if not os.path.exists(LOCAL_BASE_DIR + MUSIC_DIR):
        logging.info("Creating directory for destination media")
        os.makedirs(LOCAL_BASE_DIR + MUSIC_DIR)
    
    if PLAYLIST_DIR is not None and not os.path.exists(LOCAL_BASE_DIR + PLAYLIST_DIR):
        logging.info("Creating directory for local playlists")
        os.makedirs(LOCAL_BASE_DIR + PLAYLIST_DIR)
    
    if not os.path.exists(temp_playlist_dir):
        logging.info("Creating directory for local export")
        os.makedirs(temp_playlist_dir)

    #export rhythmbox playlists  
    subprocess.call('rhythmbox-client --no-present', shell=True)
    logging.info('Pausing %d seconds for Rhythmbox initialization' % (rhythmbox_startup_wait))
    time.sleep(rhythmbox_startup_wait) # rhythmbox isn't ready until shortly after rhythmbox-client returns
    export_playlists()
        
    #copy all files in those playlists to destination dir, and export edited version of the playlists refering to the new source
    sync_playlist_media()
   

    #cleanup
    logging.info("Removing folder used for local export")
    subprocess.call('rm -rf %s' % (temp_playlist_dir), shell=True)
  

def export_playlists():
  logging.info("Exporting playlists...")
  clean_names_regex = re.compile(r'[^\w\s]')
  sessionBus = dbus.SessionBus()
  playlistManager = sessionBus.get_object('org.gnome.Rhythmbox3', '/org/gnome/Rhythmbox3/PlaylistManager')
  asM3U = (PLAYLIST_FORMAT == 'M3U')
  for playlistName in playlistManager.GetPlaylists(dbus_interface='org.gnome.Rhythmbox3.PlaylistManager'):
    
    #check whether we have to sync this playlist!
    syncThis = True
    if len(SYNC_PLAYLISTS) > 0 and not playlistName in SYNC_PLAYLISTS: syncThis = False #working with whitelist, and this playlist is not on it
    if playlistName in SKIP_PLAYLISTS: syncThis = False #playlist is on blacklist, skip it
    
    if not syncThis:
        logging.info('Skipping %s' %playlistName)
        continue
    
    #Try to sync the playlist
    filename = "%s.%s" % (re.sub(clean_names_regex, '_', playlistName), PLAYLIST_FORMAT.lower())
    logging.info("Exporting '%s' to '%s'" % (playlistName, filename))
    try:
        fileURI = 'file://%s/%s' % (temp_playlist_dir, filename)
        logging.debug("URI: %s" % (fileURI))
        playlistManager.ExportPlaylist(playlistName, fileURI, asM3U, dbus_interface='org.gnome.Rhythmbox3.PlaylistManager')
    except dbus.exceptions.DBusException as ex:
        logging.error("Failed to export playlist: %s" % (playlistName))
        if ex.get_dbus_name().find('Error.NoReply') > -1:
            logging.error("Perhaps it was empty?  Attempting to restart Rhythmbox...")
            subprocess.call('rhythmbox-client --no-present')
            logging.info('Pausing %d seconds for Rhythmbox initialization' % (rhythmbox_startup_wait))
            time.sleep(rhythmbox_startup_wait) # rhythmbox isn't ready until shortly after rhythmbox-client returns
            playlistManager = sessionBus.get_object('org.gnome.Rhythmbox3', '/org/gnome/Rhythmbox3/PlaylistManager')
        else:
            logging.error("%s:%s" % (ex.get_dbus_name(), ex.get_dbus_message()))
            break

    

def sync_playlist_media():
  logging.info("Syncing playlists and media...")
  for filename in glob.glob("%s/*.%s" % (temp_playlist_dir, PLAYLIST_FORMAT.lower())):
    playlist = open(filename, 'r')  
    playlist_text = playlist.readlines()
    playlist.close()
    playlist_text_out = []
    playlist_name = os.path.splitext(path_leaf(filename))[0]
        
    if EACH_PLAYLIST_IN_SEPARATE_DIR:        
        playlist_line_base = '../' + MUSIC_DIR + playlist_name + '/'
        destination_base = '%s%s/' % (LOCAL_BASE_DIR + MUSIC_DIR, playlist_name) 
        
        if not os.path.exists(destination_base):
            logging.info("Creating folder for playlist %s" % (playlist_name))
            os.makedirs(destination_base)
    else:
        playlist_line_base = '../' + MUSIC_DIR
        destination_base = LOCAL_BASE_DIR + MUSIC_DIR
    
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
        
        if CONVERT_FLAC_TO_MP3 and fname.endswith('.flac'): 
            if not os.path.isfile(destination_path + fname.replace('.flac', '.mp3')):            
                fname = fname.replace('.flac', '.mp3')
                cmd = 'sox \"%s\" \"%s\"' % (source_path, destination_path + fname) #use sox to convert the source flac, and save it as mp3 to destionation dir
            else:
                logging.info('skipping %s, mp3 version of file was already created on a previous run' % (fname))
        else:
            cmd = 'cp -u \"%s\" \"%s\"' % (source_path, destination_path)

        #add converted path to new playlist
        playlist_text_out.append(playlist_line_prefix + fname + '\n') 
      
        #copy file to destination!
        logging.info('Executing: %s' % (cmd))
        subprocess.call(cmd, shell=True)

        
        #save playlist file
    if PLAYLIST_DIR is not None:
        playlist_out = open("%s/%s" % (LOCAL_BASE_DIR + PLAYLIST_DIR, filename[filename.rfind('/')+1:]), 'w')
        playlist_out.writelines(playlist_text_out)
        playlist_out.close()

#return the last part of a path (generally, the filename)
def path_leaf(path):
    head, tail = ntpath.split(path)
    return tail or ntpath.basename(head)

#sync the local copy to the target directory
def sync_local_copy_with_target():
    if not os.path.exists(TARGET_BASE_DIR):
        logging.warn("target folder is not mounted: %s" % (TARGET_BASE_DIR))
        return
        
    if not os.path.exists(TARGET_BASE_DIR + MUSIC_DIR):
        logging.warn("Music directory does not exist on target: %s" % (TARGET_BASE_DIR + MUSIC_DIR))
        return
        
  
    cmd = 'rsync -avhO --no-times --no-perms --delete --ignore-existing \"%s\" \"%s\"' % (LOCAL_BASE_DIR + MUSIC_DIR, TARGET_BASE_DIR + MUSIC_DIR)
    logging.info('Executing: %s' % (cmd))
    subprocess.call(cmd, shell=True)

    if PLAYLIST_DIR is not None: 
        if not os.path.exists(TARGET_BASE_DIR + PLAYLIST_DIR):
            logging.info("Creating directory for target playlists at %s " % (TARGET_BASE_DIR + PLAYLIST_DIR))
            os.makedirs(TARGET_BASE_DIR + PLAYLIST_DIR)
        
        #sync playlists
        cmd = 'rsync -avhO --no-times --no-perms --delete \"%s\" \"%s\"' % (LOCAL_BASE_DIR + PLAYLIST_DIR, TARGET_BASE_DIR + PLAYLIST_DIR)
        logging.info('Executing: %s' % (cmd))
        subprocess.call(cmd, shell=True)

if SYNC_TO_LOCAL_DIR:
    rhythmbox_export_playlists_to_local_copy()

if SYNC_LOCAL_TO_TARGET:
    sync_local_copy_with_target()

