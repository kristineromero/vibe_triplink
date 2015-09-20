import urllib2
import pyen
from threading import Thread
import json
from flask import Flask, jsonify, request
from random import sample
import time

app = Flask(__name__)

en = pyen.Pyen("YZZS9XI0IMOLQRKQ6")

ARTIST_QUALIFIER = 'terms' # genres
N_QUALIFIERS = 5
QUALIFIERS_MAX = 3
PARAMS_RANGE = 0.2
N_THREADS = 32
ARTIST_SAMPLE_SIZE = 15
SIMILAR_ARTIST_RETURN = 3

"""
    Author: Kristine Romero
"""

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

def find_similar_artists(artist_id):
    try:
        response = en.get('artist/similar', id = artist_id)
        similar_artists = [artist['id'] for artist in response['artists']]
        if len(similar_artists) > 3:
            return sample(similar_artists,3)
        else:
            return similar_artists
    except:
        pass

def find_similar_artists_range(artist_frequency, store):
    ranked_artist = list(reversed(sorted(artist_frequency, key=artist_frequency.get)))
    if len(ranked_artist) > SIMILAR_ARTIST_RETURN:
        ranked_artist = ranked_artist[:SIMILAR_ARTIST_RETURN]

    for artist in ranked_artist:
        if artist in store:
            return
        else:
            store[artist] = find_similar_artists(artist)
    return reduce(lambda x,y: x+y, store.values())

def get_artist_radio(artist_ids):
    artist_ids = list(artist_ids)
    similar_artists = []
    if len(artist_ids) == 1:
        response = en.get('artist/similar', id = artist_ids[0])
        similar_artists = [artist['id'] for artist in response['artists']]
    else:
        for artist in artist_ids:
            response = en.get('artist/similar', id = artist_ids)
            add_artists = [artist['id'] for artist in response['artists']]
            similar_artists.extend(add_artists)
    if len(similar_artists) > ARTIST_SAMPLE_SIZE:
        return sample(similar_artists, ARTIST_SAMPLE_SIZE)
    else:
        return similar_artists

def get_url_contents_range(url_list, store):
    for url in url_list:
        if url in store:
            return
        else:
            try:
                get_url = urllib2.urlopen(url);
                clean_page = get_url.read();
                output =  json.loads(clean_page)
                store[url] = output
            except:
                pass

def song_debug(song_list):
    song_list_meta = {}
    for i, song in enumerate(song_list):
        try:
            response = en.get('song/profile',track_id=song, bucket=['audio_summary'])
            song_list_meta[(response['songs'][0]['artist_name'] + ' - '+ response['songs'][0]['title'])] = song
        except:
            continue
    return song_list_meta

def playlist_rec_for_artist_params(similar_artist_list, params, param_range):
    a = time.time()
    playlist = []
    output_dict = {}
    acoustic = params.get('acousticness', None)
    dance = params.get('danceability', None)
    energy = params.get('energy', None)
    acoustic_max = acoustic + param_range if acoustic else 1
    acoustic_min = acoustic - param_range if acoustic else 0
    dance_max = dance + param_range if dance else 1
    dance_min = dance - param_range if dance else 0
    energy_max = energy + param_range if energy else 1
    energy_min = energy - param_range if energy else 0
    url_base = 'http://developer.echonest.com/api/v4/song/search?api_key=YZZS9XI0IMOLQRKQ6&artist_id='

    url_list = [url_base + artist + '&bucket=id:spotify-WW&bucket=tracks&sort=song_hotttnesss-desc' + \
            '&min_danceability=' + str(dance_min) + "&max_danceability=" + str(dance_max) + \
            '&min_acousticness=' + str(acoustic_min) + "&max_acousticness=" + str(acoustic_max) + \
            '&min_energy=' + str(energy_min) + "&max_energy=" + str(energy_max) + "&results=15" \
                for artist in similar_artist_list]
    b = time.time()
    track_from_url = threaded_process(N_THREADS, get_url_contents_range, url_list)
    c = time.time()
    print 'thread time: ' +str(c-b)

    # Extract unique songs from the top songs of the artist list
    keys = track_from_url.keys()
    for key in keys:
        for i, song in enumerate(track_from_url[key]['response']['songs']):
            if i >= 3:
                pass
            else:
                if song.get('tracks', None):
                    output_dict[song['title'] + '-' + song['artist_name']] = [track['foreign_id'] for track in song['tracks']][0]
    playlist = output_dict.values()

    j = time.time()
    print 'overall time: ' + str(j-a)
    return sample(playlist, len(playlist))

@app.route('/', methods = ['POST'])

def get_common_tracks():
    PARAMS = request.json['params']
    ARTIST_RADIO =  request.json['artist_radio']
    COMMON_TRACKS = request.json['common_tracks']
    if not ARTIST_RADIO:
        print 'songs'
        tic = time.time()
        SONGS =  request.json['input_list']
        song_list_info = threaded_process(N_THREADS, get_song_info_range, SONGS)
        toc = time.time()
        print 'song_list_info:', str(tic-toc)
        tic = time.time()
        song_list_info = add_song_frequency(song_list_info, SONGS)
        artist_list = get_artist_list(song_list_info)
        toc = time.time()
        print 'artist_list:', str(tic-toc)
        tic = time.time()
        artist_qualifiers = threaded_process(N_THREADS, get_artist_qualifiers_range, artist_list)
        toc = time.time()
        print 'artist_qualifiers:', str(tic-toc)
        tic = time.time()
        top_qualifiers = get_top_qualifiers(artist_qualifiers)
        toc = time.time()
        print 'top_qualifiers:', str(tic-toc)
        tic = time.time()
        artists_use = get_artist_with_qualifiers(artist_qualifiers, top_qualifiers)
        toc = time.time()
        print 'artists_use:', str(tic-toc)
        tic = time.time()
        common_tracks, artist_frequency = get_tracks(song_list_info, artists_use, PARAMS, PARAMS_RANGE)
        toc = time.time()
        print 'common_tracks:', str(tic-toc)
        tic = time.time()
        similar_artist_list = find_similar_artists_range(artist_frequency, {})
        toc = time.time()
        print 'similar_artist_list:', str(tic-toc)
        tic = time.time()
        playlist = playlist_rec_for_artist_params(similar_artist_list, PARAMS, PARAMS_RANGE)
        toc = time.time()
        print 'playlist', str(tic-toc)
        if COMMON_TRACKS:
            playlist = common_tracks + playlist
    elif ARTIST_RADIO:
        ARTISTS = request.json['input_list']
        similar_artist_list = get_artist_radio(ARTISTS)
        playlist = playlist_rec_for_artist_params(similar_artist_list, PARAMS, PARAMS_RANGE)
    playlist_output = jsonify( { 'playlist': playlist} )
    return playlist_output



if __name__ == '__main__':
    app.run(debug = True)


