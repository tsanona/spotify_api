from requests import Session
from random import choice
from string import ascii_letters, digits
import urllib.parse
from selenium.webdriver import Firefox
from base64 import b64encode
import json
from time import time
from os import path

class Auth(object):
    def __init__(self, credentials:str, tokens_loc:str = None):
        credentials = json.load(open(credentials))
        self.session = Session()
        self.user = credentials["user"]
        self.client_id = credentials["client_id"]
        self.client_secret = credentials["client_secret"]
        self.redirect_uri = credentials["redirect_uri"]
        self.show_dialog = "false" #add as opt
        self.tokens_loc = tokens_loc if tokens_loc else path.join(path.dirname(path.abspath(__file__)), "tokens.json")
        try:
            self.tokens = json.load(open(self.tokens_loc, "r"))
        except FileNotFoundError:
            self.tokens = dict()

        
    def get_code(self, scope:str):
        url = "https://accounts.spotify.com/authorize"
        state = "".join(choice(ascii_letters + digits) for i in range(10))
        parameters = urllib.parse.urlencode({"client_id":self.client_id, "response_type":"code", "redirect_uri":self.redirect_uri, "state":state, "scope":scope, "show_dialog": self.show_dialog})
        with Firefox() as driver:
            driver.get(url + "?" + parameters)
            while self.redirect_uri + "?code" not in driver.current_url:
                continue
            response = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(driver.current_url).query))
            driver.close()
        if response["state"] != state:
            raise Exception("State missmatch, possible man in the middle atack, please try again.")
        return response["code"]

    def get_new_token(self, scope:str, refresh:bool):
        url = "https://accounts.spotify.com/api/token"
        header = b64encode((self.client_id + ':' + self.client_secret).encode("ascii")).decode('ascii')
        if refresh:
            data = {"grant_type":"refresh_token", "refresh_token":json.load(open(self.tokens_loc, "r"))["refresh_token"], "scope":scope} if scope else {'grant_type': 'client_credentials'}
        else:
            data = {"grant_type":"authorization_code", "code":self.get_code(scope), "redirect_uri":self.redirect_uri} if scope else {'grant_type': 'client_credentials'}
        token = self.session.request("POST", url, data=data, headers={"Authorization": f"Basic {header}"})
        token = token.json()
        token["expires_at"] = time() + token["expires_in"]
        return token
    
    def get_token(self, scope:str=None):
        url = "https://accounts.spotify.com/api/token"
        header = b64encode((self.client_id + ':' + self.client_secret).encode("ascii")).decode('ascii')
        if not self.tokens: 
            token = self.get_new_token(scope, False)
            self.tokens = token
            json.dump(token, open("tokens.json", "w"))
        elif self.tokens["expires_at"] - time() < 60 or str(scope) not in self.tokens["scope"]: #Refresh scope #WARNING if first token has no token then refresh will not work.
            token = self.get_new_token(scope, True)
            token["expires_at"] = time() + token["expires_in"]
            self.tokens = token
        if "refresh_token" in list(self.tokens):
            json.dump(self.tokens, open(self.tokens_loc, "w"))
        token = self.tokens
        return token              
        
class Api(object):
    def __init__(self, auth_credentials:dict, tokens_loc:str = None):
        self.base_url = "https://api.spotify.com/v1/"
        self.session = Session()
        self.session.headers.update({"Accept": "application/json", "Content-Type": "application/json"})
        self.auth = Auth(auth_credentials, tokens_loc)
            
    @staticmethod
    def _parse_params(kwargs:dict):
        new = dict()
        delete = list()
        for key in kwargs:
            if kwargs[key] is None: #get rid of empty args
                delete.append(key)
            elif type(kwargs[key]) is list: #parse lists in details
                kwargs.update({key:",".join(kwargs[key])})
            elif type(kwargs[key]) is dict: #parse dictionaries in details
                delete.append(key)
                for key1 in kwargs[key]:
                    new.update({key+key1:kwargs[key][key1]})
        for key2 in delete:
            kwargs.pop(key2)
        kwargs.update(new)
        return kwargs
    
    @staticmethod
    def _id_to_uri(ids:list, id_type:str):
        return [f"spotify:{id_type}:{i_id}" for i_id in ids]
    
    def _request(self, request_type, url:str, scope=None, params=None, data=None):
        params = self._parse_params(params) if params else None
        data = json.dumps(data) if data else None
        token = self.auth.get_token(scope)
        return self.session.request(request_type, self.base_url + url, params=params, data=data, headers={'Authorization': f'{token["token_type"]} {token["access_token"]}'})
    
    #Albums
    def get_albums(self, album_ids:list, market:str = None):
        """
        Get Spotify catalog information for a single album.
        
        Parameters:
        
            - album_id: The Spotify ID for the album.
            - market: An ISO 3166-1 alpha-2 country code or the string from_token. Provide this parameter if you want to apply Track Relinking.
        """
        return self._request("GET", "albums", params={"ids":album_ids, "market":market})

    def get_album_tracks(self, album_id:str, limit:int=20, offset:int=0, market:str=None):
        """
        Get Spotify catalog information about an album’s tracks. Optional parameters can be used to limit the number of tracks returned.
        
        Parameters:
        
            - album_id: The Spotify ID for the album.
            - limit: The maximum number of tracks to return. Default: 20. Minimum: 1. Maximum: 50.
            - offset: The index of the first track to return. Default: 0 (the first object). Use with limit to get the next set of tracks.
            - market: An ISO 3166-1 alpha-2 country code or the string from_token. Provide this parameter if you want to apply Track Relinking.
        """
        return self._request("GET", f"albums/{album_id}/tracks", params={"limit":limit, "offset":offset, "market":market})

    #Artists
    def get_artists(self, artist_ids:list):
        """
        Get Spotify catalog information for several artists based on their Spotify IDs.
        
        Parameter:
           
            - artist_id: The Spotify ID for the album.
        """
        return self._request("GET", "artists", params={"ids":artist_ids})
    
    def get_artist_albums(self, artist_id:str, include_groups:list=None, country:str=None, limit:int=20, ofset:int=0):
        """
        Get Spotify catalog information about an artist’s albums. Optional parameters can be specified in the query string to filter and sort the response.
        
        Parameters:
            
            - artist_id: The Spotify ID for the album.
            - include_groups: A comma-separated list of keywords that will be used to filter the response. If not supplied, all album types will be returned. Valid values are:
                - album
                - single
                - appears_on
                - compilation
            - country: An ISO 3166-1 alpha-2 country code or the string from_token. Supply this parameter to limit the response to one particular geographical market.
            - limit: The maximum number of tracks to return. Default: 20. Minimum: 1. Maximum: 50.
            - offset: The index of the first track to return. Default: 0 (the first object). Use with limit to get the next set of tracks.
        """
        if include_groups:
            if list(filter(lambda x: x not in ("album", "single", "appears_on", "compilation"), include_groups)):
                raise Exception(f"{include_groups} is not a valid list of filters")
        return self._request("GET", f"artists/{artist_id}/albums", params={"include_groups":include_groups, "country":country, "limit":limit, "ofset":ofset})
    
    def get_artist_top_tracks(self, artist_id:str, country:str):
        """
        Get Spotify catalog information about an artist’s top tracks by country.
        
        Parameters:
            
            - artist_id: The Spotify ID for the album.
            - country: An ISO 3166-1 alpha-2 country code or the string from_token. Supply this parameter to limit the response to one particular geographical market.
        """
        return self._request("GET", f"artists/{artist_id}/top-tracks", params={"country":country})
    
    def get_artist_related_artists(self, artist_id:str):
        """
        Get Spotify catalog information about artists similar to a given artist. Similarity is based on analysis of the Spotify community’s listening history.
        
        Parameter:
            
            - artist_id: The Spotify ID for the album.
        """
        return self._request("GET", f"artists/{artist_id}/related-artists")
    
    #Browse
    def get_categories(self, country:str=None, locale:str=None, limit:int=20, offset:int=0):
        """
        Get a list of categories used to tag items in Spotify (on, for example, the Spotify player’s “Browse” tab).
        
        Parameters:
            
            - country: An ISO 3166-1 alpha-2 country code or the string from_token. Supply this parameter to limit the response to one particular geographical market.
            - locale: The desired language, consisting of an ISO 639-1 language code and an ISO 3166-1 alpha-2 country code, joined by an underscore.
            - limit: The maximum number of tracks to return. Default: 20. Minimum: 1. Maximum: 50.
            - offset: The index of the first track to return. Default: 0 (the first object). Use with limit to get the next set of tracks.
        """
        return self._request("GET", "browse/categories", params={"country":country, "locale":locale, "limit":limit, "offset":offset})
    
    def get_category_playlists(self, category_id:str, country:str=None, limit:int=20, offset:int=0):
        """
        Get a list of Spotify playlists tagged with a particular category.
        
        Parameters:
            
            - category_id: The Spotify category ID for the category.
            - country: An ISO 3166-1 alpha-2 country code or the string from_token. Supply this parameter to limit the response to one particular geographical market.
            - limit: The maximum number of tracks to return. Default: 20. Minimum: 1. Maximum: 50.
            - offset: The index of the first track to return. Default: 0 (the first object). Use with limit to get the next set of tracks.
        """
        return self._request("GET", f"browse/categories/{category_id}/playlists", params={"country":country, "limit":limit, "offset":offset})
    
    def get_featured_playlists(self, country:str=None, locale:str=None, timestamp:str=None, limit:int=20, offset:int=0):
        """
        Get a list of Spotify featured playlists (shown, for example, on a Spotify player’s ‘Browse’ tab).
        
        Parameters:
            
            - country: An ISO 3166-1 alpha-2 country code or the string from_token. Supply this parameter to limit the response to one particular geographical market.
            - locale: The desired language, consisting of an ISO 639-1 language code and an ISO 3166-1 alpha-2 country code, joined by an underscore.
            - timestamp: A timestamp in ISO 8601 format: yyyy-MM-ddTHH:mm:ss. Use this parameter to specify the user’s local time to get results tailored for that specific date and time in the day. If not provided, the response defaults to the current UTC time. 
            - limit: The maximum number of tracks to return. Default: 20. Minimum: 1. Maximum: 50.
            - offset: The index of the first track to return. Default: 0 (the first object). Use with limit to get the next set of tracks.
        """
        return self._request("GET", "browse/featured-playlists", params={"country":country, "locale":locale, "timestamp":timestamp, "limit":limit, "offset":offset})
    
    def get_new_releases(self, country:str=None, limit:int=20, offset:int=0):
        """
        Get a list of new album releases featured in Spotify (shown, for example, on a Spotify player’s “Browse” tab).
        
        Parameters:
            
            - country: An ISO 3166-1 alpha-2 country code or the string from_token. Supply this parameter to limit the response to one particular geographical market.
            - limit: The maximum number of tracks to return. Default: 20. Minimum: 1. Maximum: 50.
            - offset: The index of the first track to return. Default: 0 (the first object). Use with limit to get the next set of tracks.
        """
        return self._request("GET", "browse/new-releases", params={"country":country, "limit":limit, "offset":offset})
    
    def get_recommendations(self, seed_artists:list=None, seed_genres:list=None, seed_tracks:list=None, limit:int=20, market:str=None, max_:dict=None, min_:dict=None, target_:dict=None):
        """
        Create a playlist-style listening experience based on seed artists, tracks and genres.
        
        Parameters:
            
            - seed_artists: A comma separated list of Spotify IDs for seed artists. Up to 5 seed values may be provided in any combination of seed_artists, seed_tracks and seed_genres.
            - seed_genres: A comma separated list of any genres in the set of available genre seeds. Up to 5 seed values may be provided in any combination of seed_artists, seed_tracks and seed_genres.
            - seed_tracks: A comma separated list of Spotify IDs for a seed track. Up to 5 seed values may be provided in any combination of seed_artists, seed_tracks and seed_genres.
            - limit: The target size of the list of recommended tracks. For seeds with unusually small pools or when highly restrictive filtering is applied, it may be impossible to generate the requested number of recommended tracks. Debugging information for such cases is available in the response. Default: 20. Minimum: 1. Maximum: 100.
            - market: An ISO 3166-1 alpha-2 country code or the string from_token. Provide this parameter if you want to apply Track Relinking. Because min_*, max_* and target_* are applied to pools before relinking, the generated results may not precisely match the filters applied. Original, non-relinked tracks are available via the linked_from attribute of the relinked track response.
            - max_*: Multiple values. For each tunable track attribute, a hard ceiling on the selected track attribute’s value can be provided. See tunable track attributes below for the list of available options.
            - min_*: Multiple values. For each tunable track attribute, a hard floor on the selected track attribute’s value can be provided. See tunable track attributes below for the list of available options.
            - target_*: Multiple values. For each of the tunable track attributes (below) a target value may be provided. Tracks with the attribute values nearest to the target values will be preferred.
        """
        #TODO seed not to be both necessary
        if not (seed_artists or seed_genres or seed_tracks):
            raise Exception("At least one seed has to be given.")
        return self._request("GET", "recommendations", params={"seed_artists":seed_artists, "seed_genres":seed_genres, "seed_tracks":seed_tracks, "limit":limit, "market":market, "max_":max_, "min_":min_, "target_":target_})

    #Episodes
    def get_episodes(self, ids:list, market:str = None):
        """
        Get Spotify catalog information for multiple episodes based on their Spotify IDs.
        
        Parameters:
        
            - ids: A comma-separated list of the Spotify IDs for the episodes. Maximum: 50 IDs.
            - market: An ISO 3166-1 alpha-2 country code or the string from_token. Provide this parameter if you want to apply Track Relinking.
        """
        return self._request("GET", "episodes", params={"ids":ids, "market":market})
    
    #Follow
    def get_if_user_follows(self, type_of:str, ids:list):
        """
        Check to see if the current user is following one or more artists or other Spotify users.
        
        Parameters:
            
            - type_of: The ID type: either artist or user.
            - ids: A comma-separated list of the artist or the user Spotify IDs to check.  A maximum of 50 IDs can be sent in one request.
        """
        if type_of not in ("artist", "user"):
            raise Exception(f"{type_of} is not a valid type")
        return self._request("GET", "me/following/contains", "user-follow-read", params={"type":type_of, "ids":ids})
    
    def get_if_users_follow_playlist(self, playlist_id:str, ids:list):
        """
        Check to see if one or more Spotify users are following a specified playlist.
        
        Parameters:
            
            - playlist_id: The Spotify ID of the playlist. Use "current_user" for current user.
            - ids: A comma-separated list of Spotify User IDs; the ids of the users that you want to check to see if they follow the playlist. Maximum: 5 ids. Use "current_id" to use current user.
        """
        if "current_user" in ids:
            ids = [self.auth.user if x == "current_user" else x for x in ids]
        return self._request("GET", f"playlists/{playlist_id}/followers/contains", "playlist-read-private", params={"ids":ids})
    
    def follow(self, type_of:str, ids:list, delete:bool):
        """
        Add/Remove the current user as a follower of one or more artists or other Spotify users.
        
        Parameters:
            
            - type_of: The ID type: either artist or user.
            - ids: A comma-separated list of the artist or the user Spotify IDs to check.  A maximum of 50 IDs can be sent in one request.
            - delete: Boolean value that tells wheather to delete or add artist/users
        """
        verb = "DELETE" if delete else "PUT"
        if type_of not in ("artist", "user"):
            raise Exception(f"{type_of} is not a valid type")
        return self._request(verb, "me/following", "user-follow-modify", params={"type":type_of, "ids":ids})
    
    def follow_playlist(self, playlist_id:str, delete:bool, public:str="true"):
        """
        Add the current user as a follower of a playlist.
        
        Parameters:
            
            - playlist_id: The Spotify ID of the playlist. Any playlist can be followed, regardless of its public/private status, as long as you know its playlist ID.
            - public: Defaults to true. If true the playlist will be included in user’s public playlists, if false it will remain private.
        """
        verb = "DELETE" if delete else "PUT"
        return self._request(verb, f"playlists/{playlist_id}/followers", "playlist-modify-private playlist-modify-public", data = {"public":public})
    
    def get_user_followed(self, type_of:str, limit:int=20, after:str=None):
        """
        Get the current user’s followed artists.
        
        Parameters:
            
            - type_of: The ID type: currently only artist is supported.
            - limit: The maximum number of items to return. Default: 20. Minimum: 1. Maximum: 50.
            - after: The last ID retrieved from the previous request.
        """
        if type_of not in ("artist"):
            raise Exception(f"{type_of} is not a valid type")
        return self._request("GET", "me/following", "user-follow-read", params={"type":type_of, "after":after})
    
    #Library
    def get_if_user_saved(self, type_of:str, ids:list):
        """
        Check if one or more albums/tracks/shows is already saved in the current Spotify user’s ‘Your Music’ library.
        
        Parameters:
        
            - type of: albums, tracks or shows
            - ids: A comma-separated list of the Spotify IDs for the albums/tracks. Maximum: 50 IDs.
        """
        if type_of not in ("albums", "tracks", "shows"):
            raise Exception(f"{type_of} is not a valid type")
        return self._request("GET", f"me/{type_of}/contains", "user-library-read", params={"ids":ids})
    
    def get_user_saved(self, type_of:str, limit:int=20, offset:int=0, market:str=None):
        """
        Get a list of the albums/tracks/shows saved in the current Spotify user’s ‘Your Music’ library.
        
        Parameters:
        
            - type of: albums, tracks or shows
            - limit: The maximum number of objects to return. Default: 20. Minimum: 1. Maximum: 50.
            - offset: The index of the first object to return. Default: 0 (i.e., the first object). Use with limit to get the next set of objects.
            - market: An ISO 3166-1 alpha-2 country code or the string from_token.
        """
        if type_of not in ("albums", "tracks", "shows"):
            raise Exception(f"{type_of} is not a valid type")
        return self._request("GET", f"me/{type_of}", "user-library-read", params={"limit":limit, "offset":offset, "market":market})
    
    def library(self, type_of:str, ids:list, delete:bool):
        """
        Save/Remove one or more albums/tracks/shows from the current user’s ‘Your Music’ library.
        
        Parameters:
        
            - type of: albums, tracks or shows
            - ids: A comma-separated list of the Spotify IDs.
            - delete: True to remove, False to save.
        """
        verb = "Delete" if delete else "PUT"
        if type_of not in ("albums", "tracks", "shows"):
            raise Exception(f"{type_of} is not a valid type")
        return self._request(verb, f"me/{type_of}", params={"ids":ids})
    
    #Personalization
    def get_user_top(self, type_of:str, limit:int=20, offset:int=0, time_range:str="medium_term"):
        """
        Get the current user’s top artists or tracks based on calculated affinity.
        
        Parameters:
        
            - type of: 	The type of entity to return. Valid values: artists or tracks.
            - limit: The number of entities to return. Default: 20. Minimum: 1. Maximum: 50. 
            - offset:  The index of the first entity to return. Default: 0 (i.e., the first track). Use with limit to get the next set of entities.
            - time range: Over what time frame the affinities are computed. Valid values: long_term (calculated from several years of data and including all new data as it becomes available), medium_term (approximately last 6 months), short_term (approximately last 4 weeks). Default: medium_term.
        """
        if type_of not in ("artists", "tracks"):
            raise Exception(f"{type_of} is not a valid type")
        return self._request("GET", f"me/top/{type_of}", "user-top-read", params={"limit":limit, "offset":offset, "time_range":time_range})
    
    #Player
    def playback_add_queue_item(self, uri:str, device_id:str=None):
        """
        Add an item to the end of the user’s current playback queue.
        
        Parameters:
        
            - uri: The uri of the item to add to the queue. Must be a track or an episode uri.
            - device id: The id of the device this command is targeting. If not supplied, the user’s currently active device is the target.
        """
        return self._request("POST", "me/player/queue", "user-modify-playback-state" , params={"uri":uri, "device_id":device_id})
    
    def get_user_available_devices(self):
        """
        Get information about a user’s available devices.
        """
        return self._request("GET", "me/player/devices", "user-read-playback-state")
    
    def get_playback_info(self, market:str=None):
        """
        Get information about the user’s current playback state, including track, track progress, and active device.
        
        Parameters:

            - market: An ISO 3166-1 alpha-2 country code or the string from_token.
        """
        return self._request("GET", "me/player", "user-read-playback-state", params={"market":market})
    
    def get_recently_played_tracks(self, limit:int=20, after:int=None, before:int=None):
        """
        Get tracks from the current user’s recently played tracks.
        
        Parameters:
        
            - limit: The maximum number of items to return. Default: 20. Minimum: 1. Maximum: 50.
            - after: A Unix timestamp in milliseconds. Returns all items after (but not including) this cursor position. If after is specified, before must not be specified.
            - before: A Unix timestamp in milliseconds. Returns all items before (but not including) this cursor position. If before is specified, after must not be specified.
        """
        if after and before:
            raise Exception("Only either after or before can be specified")
        return self._request("GET", "me/player/recently-played", "user-read-recently-played", params={"limit":limit, "after":after, "before":before})
    
    def get_currently_playing_track(self, market:str=None):
        """
        Get the object currently being played on the user’s Spotify account.
        
        Parameters:
        
            - market: An ISO 3166-1 alpha-2 country code or the string from_token.
        """
        return self._request("GET", "me/player/currently-playing", "user-read-playback-state", params={"market":market})
    
    def playback_control(self, action:str, device_id:str=None):
        """
        Play/Pause/Skips playback on the user’s account.
        
        Parameters:
        
            - action: Name of control:
                - play;
                - pause;
                - next;
                - previous;
            - device id: The id of the device this command is targeting. If not supplied, the user’s currently active device is the target.
        """
        verb = "PUT" if action in ("play", "pause") else "POST" if action in ("next","previous") else None
        if verb is None:
            raise Exception(f"{action} is not a valid action")
        return self._request(verb, f"me/player/{action}", "user-modify-playback-state", params={"device_id":device_id})
    
    def playback_track_position(self, position_ms:int, device_id:str=None):
        """
        Seeks to the given position in the user’s currently playing track.
        
        Parameters:
        
            - position ms: The position in milliseconds to seek to. Must be a positive number. Passing in a position that is greater than the length of the track will cause the player to start playing the next song.
            - device id: The id of the device this command is targeting. If not supplied, the user’s currently active device is the target.
        """
        return self._request("PUT", "me/player/seek", "user-modify-playback-state", params={"position_ms":position_ms, "device_id":device_id})
    
    def playback_mode(self, mode:str, state:str, device_id:str=None):
        """
        Set the repeat mode for the user’s playback. Options are repeat-track, repeat-context, and off.
        
        Parameters:
        
            - mode: mode to change the state of. Possible values:
                - repeat
                - shuffle
            - state: Possible states for:
                - repeat:
                    - track: will repeat the current track;  
                    - context: will repeat the current context;
                    - off: will turn repeat off;
                - shuffle:
                    - true : Shuffle user’s playback;
                    - false : Do not shuffle user’s playback;
            - device_id: The id of the device this command is targeting. If not supplied, the user’s currently active device is the target.
        """
        if mode not in ("repeat", "shuffle"):
            raise Exception(f"{mode} is not a valid mode")
        states = {"repeat":("track", "context", "off"), "shuffle":("true", "false")}
        if state not in states["mode"]:
            raise Exception(f"{state} is not a valid state for {mode}")
        return self._request("PUT", f"me/player/{mode}", "user-modify-playback-state", params={"state":state, "device_id":device_id})
    
    def playback_volume(self, volume_percent:int, device_id:str=None):
        """
        Set the volume for the user’s current playback device.
        
        Parameters:
        
            - volume_percent: The volume to set. Must be a value from 0 to 100 inclusive.
            - device_id: The id of the device this command is targeting. If not supplied, the user’s currently active device is the target.
        """
        return self._request("PUT", "me/player/volume", "user-modify-playback-state", params={"volume_percent":volume_percent, "device_id":device_id})
    
    def playback_tranfer(self, device_ids:str, play:bool=None):
        """
        Transfer playback to a new device and determine if it should start playing.
        
        Parameters:
        
            - device_ids: A JSON array containing the ID of the device on which playback should be started/transferred. Although an array is accepted, only a single device_id is currently supported.
            - play: 
                - true: ensure playback happens on new device;
                - false or not provided: keep the current playback state;
        """
        return self._request("PUT", "me/player", "user-modify-playback-state", data={"device_ids":device_ids, "play":play})
      
    #Playlists
    def playlist_add_track(self, playlist_id:str, track_ids:list, position:int=None):
        """
        Add one or more tracks to a user’s playlist.
        
        Parameters:
        
            - playlist id: The Spotify ID for the playlist.
            - track ids: list of track
            - position: The position to insert the tracks, a zero-based index. If omitted, the tracks will be appended to the playlist.
        """
        return self._request("POST", f"playlists/{playlist_id}/tracks", "playlist-modify-private playlist-modify-public", params={"track_ids":self._id_to_uri(track_ids, "tracks"), "position":position})
    
    def playlist_details(self, playlist_id:str, name:str=None, public:str=None, collaborative:str=None, description:str=None):
        """
        Change a playlist’s name and public/private state. (The user must, of course, own the playlist.)
        
        Parameters:
        
            - playlist_id: The Spotify ID for the playlist.
            - name:  The new name for the playlist;
            - public: If true the playlist will be public, if false it will be private.
            - collaborative: If true , the playlist will become collaborative and other users will be able to modify the playlist in their Spotify client. Note: You can only set collaborative to true on non-public playlists.
            - description: Value for playlist description as displayed in Spotify Clients and in the Web API.
        """
        return self._request("PUT", f"playlists/{playlist_id}", "playlist-modify-private playlist-modify-public", data={"name":name, "public":public, "collaborative":collaborative, "description":description})
    
    def playlist_create(self, name:str, public:str=None, collaborative:str=None, description:str=None):
        """
        Create a playlist for a Spotify user. (The playlist will be empty until you add tracks.)
        
        Parameters:

            - name: The name for the new playlist. This name does not need to be unique; a user may have several playlists with the same name.
            - public: If true the playlist will be public, if false it will be private.
            - collaborative: If true , the playlist will become collaborative and other users will be able to modify the playlist in their Spotify client. Note: You can only set collaborative to true on non-public playlists.
            - description: Value for playlist description as displayed in Spotify Clients and in the Web API.
        """
        return self._request("POST", f"users/{self.auth.user}/playlists", "playlist-modify-private playlist-modify-public", data={"name":name, "public":public, "collaborative":collaborative, "description":description})
    
    def get_playlist_list(self, user_id:str, limit:int=20, offset:int=0):
        """
        Get a list of the playlists owned or followed by the current Spotify user.
        
        Parameters:
        
            - user_id: The user’s Spotify user ID. Use "current_user" for current user.
            - limit: The maximum number of playlists to return. Default: 20. Minimum: 1. Maximum: 50.
            - offset: The index of the first playlist to return. Default: 0 (the first object). Maximum offset: 100.000. Use with limit to get the next set of playlists.
        """
        return self._request("GET", f"users/{user_id}/playlists", "playlist-read-private playlist-read-collaborative")
 
    def get_playlist(self, playlist_id:str, fields:list=None, market:str=None):
        """
        Get a playlist owned by a Spotify user.
        
        Parameters:
        
            - playlist_id: The Spotify ID for the playlist.
            - fields: ilters for the query: a comma-separated list of the fields to return. If omitted, all fields are returned. For example, to get just the playlist’s description and URI: fields=description,uri. A dot separator can be used to specify non-reoccurring fields, while parentheses can be used to specify reoccurring fields within objects. For example, to get just the added date and user ID of the adder: fields=tracks.items(added_at,added_by.id). Use multiple parentheses to drill down into nested objects, for example: fields=tracks.items(track(name,href,album(name,href))). Fields can be excluded by prefixing them with an exclamation mark, for example: fields=tracks.items(track(name,href,album(!name,href)))
            - market: An ISO 3166-1 alpha-2 country code or the string from_token.
        """
        return self._request("GET", f"playlists/{playlist_id}", params={"fields":fields, "market":market})
    
    def get_playlist_cover_image(self, playlist_id:str):
        """
        Get the current image associated with a specific playlist.
        
        Parameters:
        
            - playlist_id: The Spotify ID for the playlist.
        """
        return self._request("GET", f"playlists/{playlist_id}/images")
    
    def get_playlist_tracks(self, playlist_id:str, fields:list=None, limit:int=100, offset:int=0, market:str=None):
        """
        Get full details of the tracks of a playlist owned by a Spotify user.
        
        Parameters
        
            - playlist_id: The Spotify ID for the playlist.
            - fields: Filters for the query: a comma-separated list of the fields to return. If omitted, all fields are returned. For example, to get just the total number of tracks and the request limit:
            fields=total,limit
            A dot separator can be used to specify non-reoccurring fields, while parentheses can be used to specify reoccurring fields within objects. For example, to get just the added date and user ID of the adder:
            fields=items(added_at,added_by.id)
            Use multiple parentheses to drill down into nested objects, for example:
            fields=items(track(name,href,album(name,href)))
            Fields can be excluded by prefixing them with an exclamation mark, for example:
            fields=items.track.album(!external_urls,images)
            - limit: he maximum number of tracks to return. Default: 100. Minimum: 1. Maximum: 100.
            - offset: The index of the first playlist to return. Default: 0 (the first object). Maximum offset: 100.000. Use with limit to get the next set of playlists.
            - market: An ISO 3166-1 alpha-2 country code or the string from_token.
        """
        return self._request("GET", f"playlists/{playlist_id}/tracks", "playlist-read-private playlist-read-collaborative", params={"fields":fields, "limit":limit, "offset":offset, "market":market})
    
    def playlist_remove_track(self, playlist_id:str, track_ids:list):
        """
        Remove one or more tracks from a user’s playlist.
        
        Parameters:
        
            - playlist id: The Spotify ID for the playlist.
            - track ids: list of track
        """
        return self._request("DELETE", f"playlists/{playlist_id}/tracks", "playlist-modify-private playlist-modify-public", params={"track_ids":self._id_to_uri(track_ids, "tracks")})
    
    #Reorder,Replace,Custom Playlist Cover
    
    #Search
    
    #Shows
    
    #Tracks
    def get_audio_analysis(self, track_id:str):
        """
        Get a detailed audio analysis for a single track identified by its unique Spotify ID.
        
        Parameters:
        
            - track id: The Spotify ID for the track.
        """
        return self._request("GET", f"audio-analysis/{track_id}")
    
    def get_audio_features(self, track_ids:list):
        """
        Get audio features for multiple tracks based on their Spotify IDs.
        
        Parameters:

            -track ids: A comma-separated list of the Spotify IDs for the tracks. Maximum: 100 IDs.
        """
        return self._request("GET", "audio-features", params={"ids":track_ids})
    
    def get_tracks(self, track_ids:list, market=None):
        """
        Get Spotify catalog information for multiple tracks based on their Spotify IDs.
        
        Parameters:
        
            - track ids: A comma-separated list of the Spotify IDs for the tracks. Maximum: 50 IDs.
            - market: An ISO 3166-1 alpha-2 country code or the string from_token.
        """
        return self._request("GET", "traks", params={"ids":track_ids, "market":market})
    
    #User Profile
    def get_user_profile(self, user_id:str):
        """
        Get public profile information about a Spotify user.
        
        Parameters:
        
            - user_id: The user’s Spotify user ID.
        """
        return self._request("GET", "users", params={"user_id":user_id})


