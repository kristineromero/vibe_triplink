import urllib
import pyen
from threading import Thread
import json
from flask import Flask, jsonify, request

app = Flask(__name__)

en = pyen.Pyen("YZZS9XI0IMOLQRKQ6")

ARTIST_QUALIFIER = 'terms' # genres
N_QUALIFIERS = 5
QUALIFIERS_MAX = 3
PARAMS_RANGE = 0.2
N_THREADS = 4

def get_song_frequency(song_list):
    song_frequency = {}
    for song in song_list:
        if song in song_frequency:
            song_frequency[song] += 1
        else:
            song_frequency[song] = 1
    return song_frequency

def get_song_info(song):
    song_id = None
    artist_id = None
    acousticness = None
    danceability = None
    energy = None
    try:
        response = en.get('song/profile',track_id=song, bucket=['audio_summary'])
        artist_id = response['songs'][0].get('artist_id', None)
        song_id = response['songs'][0].get('id', None)
        if 'audio_summary' in response['songs'][0]:
            acousticness = response['songs'][0]['audio_summary'].get('acousticness', None)
            danceability = response['songs'][0]['audio_summary'].get('danceability', None)
            energy = response['songs'][0]['audio_summary'].get('energy', None)
    except:
        pass
    return {'song_id' : song_id,
            'artist_id' : artist_id,
            'acousticness' : acousticness,
            'danceability' : danceability,
            'energy' : energy}

def get_song_info_range(song_list, store):
    """process a list of ids for threading"""
    for song in song_list:
        if song in store:
            return
        else:
            store[song] = get_song_info(song)

def threaded_process(nthreads, function, input_list):
    """process the id range in a specified number of threads"""
    threads = []
    store = {}
    # create the threads
    if nthreads > len(input_list):
        nthreads = len(input_list)

    for i in range(nthreads):
        input_list_subset = input_list[i::nthreads]
        t = Thread(target=function, args=(input_list_subset, store))
        threads.append(t)
    # start the threads
    [ t.start() for t in threads ]
    # wait for the threads to finish
    [ t.join(1) for t in threads ]
    return store

def add_song_frequency(song_list_info, song_list):
    for song in song_list_info:
        song_frequencies = get_song_frequency(song_list)
        song_list_info[song]['frequency'] = song_frequencies[song]
    return song_list_info


def get_artist_list(song_list_info):
    artists = []
    for song in song_list_info:
        artists.append(song_list_info[song]['artist_id'])
    return list(set(artists))

def get_artist_qualifiers(artist_id):
    qualifiers = []
    qualifier_arg = 'artist/' + ARTIST_QUALIFIER
    try:
        response = en.get(qualifier_arg, id = artist_id)
        if ARTIST_QUALIFIER == 'terms':
            for i in range(N_QUALIFIERS):
                qualifiers.append(response['terms'][i]['name'])
        elif ARTIST_QUALIFIER == 'genres':
            qualifiers = [response['terms']['genre'], response['terms']['sub_genre']]
    except:
        pass
    return qualifiers

def get_artist_qualifiers_range(artist_list, store, *args):
    for artist in artist_list:
        if artist in store:
            return
        else:
            store[artist] = get_artist_qualifiers(artist)

def get_top_qualifiers(artist_qualifiers):
    qualifiers_dict = {}
    for artist in artist_qualifiers:
        for qualifier in artist_qualifiers[artist]:
            if qualifier in qualifiers_dict:
                qualifiers_dict[qualifier] += 1
            else:
                qualifiers_dict[qualifier] = 1
    top_qualifiers = list(reversed(sorted(qualifiers_dict, key=qualifiers_dict.get)))
    if len(top_qualifiers) < QUALIFIERS_MAX:
        return top_qualifiers
    else:
        return top_qualifiers[0:QUALIFIERS_MAX]

def get_artist_with_qualifiers(artist_qualifiers, top_qualifiers):
    common_artists = []
    for artist in artist_qualifiers:
        for term in artist_qualifiers[artist]:
            if term in top_qualifiers:
                common_artists.append(artist)
    return list(set(common_artists))


def get_tracks(song_list_info, artists_use, params, param_range):
    spotify_track_ids = []
    artist_frequency = {}
    acoustic = params.get('acousticness', None)
    dance = params.get('danceability', None)
    energy = params.get('energy', None)
    acoustic_max = acoustic + param_range if acoustic else None
    acoustic_min = acoustic - param_range if acoustic else None
    dance_max = dance + param_range if dance else None
    dance_min = dance - param_range if dance else None
    energy_max = energy + param_range if energy else None
    energy_min = energy - param_range if energy else None
    for song in song_list_info:
        artist = song_list_info[song]['artist_id']
        acoustic_val = song_list_info[song]['acousticness']
        dance_val = song_list_info[song]['danceability']
        energy_val = song_list_info[song]['energy']
        if song_list_info[song]['artist_id'] in artists_use:
            if acoustic_min < acoustic_val < acoustic_max or not acoustic_min:
                if dance_min < dance_val < dance_max or not dance_min:
                    if energy_min < energy_val < energy_max or not energy_min:
                        if artist in artist_frequency:
                            artist_frequency[artist] += 1
                            if artist_frequency[artist] < 3:
                                spotify_track_ids.append(song)
                        else:
                            artist_frequency[artist] = 1
                            spotify_track_ids.append(song)

    return spotify_track_ids, artist_frequency

@app.route('/', methods = ['POST'])

def get_common_tracks():
    songs =  request.json['songs']
    params = request.json['params']
    song_list_info = threaded_process(N_THREADS, get_song_info_range, songs)
    song_list_info = add_song_frequency(song_list_info, songs)
    artist_list = get_artist_list(song_list_info)
    artist_qualifiers = threaded_process(N_THREADS, get_artist_qualifiers_range, artist_list)
    top_qualifiers = get_top_qualifiers(artist_qualifiers)
    artists_use = get_artist_with_qualifiers(artist_qualifiers, top_qualifiers)
    common_tracks, artist_frequency = get_tracks(song_list_info, artists_use, params, PARAMS_RANGE)
    playlist = jsonify( { 'playlist': common_tracks} )
    return playlist

if __name__ == '__main__':
    app.run(debug = True)


