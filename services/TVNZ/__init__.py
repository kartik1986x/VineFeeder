# TVNZ __init__.py
from base_loader import BaseLoader
from parsing_utils import extract_params_json, split_options, prettify
from rich.console import Console
import subprocess
import sys
import jmespath
import json
from beaupy import select_multiple

console = Console()

# TV Shows https://www.tvnz.co.nz/shows/boiling-point/episodes/s1-e1 or
# Movies https://www.tvnz.co.nz/shows/legally-blonde/movie/s1-e1 or 
# Sport https://www.tvnz.co.nz/sport/football/uefa-euro/spain-v-france-semi-finals-highlights

class TvnzLoader(BaseLoader):  

    # global options 
    options = ''



    def __init__(self):
        """
        Initialize the All4Loader class with the provided headers.

        Parameters:
            None

        Attributes:
            options (str): Global options; later taken from service config.yaml
            headers (dict): Global headers; may be overridden
        """ 
        
        headers = {
            'Accept': '*/*',
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64)',
            #'Origin': 'https://www.tvnz.co.nz',
            #'Referer': 'https://www.tvnz.co.nz',
        }
        super().__init__(headers)
        self.showType = None


    # entry point from Vinefeeder
    def receive(self, inx: None, search_term: None, category=None, hlg_status=False, opts=None): 
   
        """
        First fetch for series titles matching all or part of search_term.
        
        Uses inx, an int variable to switch:-
            0 for greedy search using url
            1 for direct url download
            2 for category browse 
            3 for search with keyword
        If search_url_entry is left blank vinefeeder generates a 
        a menu with 3 options:
            - Greedy Search by URL
            - Browse by Category
            - Search by Keyword
        results are forwarded to receive().
        If inx == 1, do direct download using url.
        If inx == 3, do keyword search.
        If inx == 0, fetch videos using a greedy search or browse-category.
        If inx == 2, fetch videos from a category url.
        If an unknown error occurs, exit with code 0.
        """

        # re-entry here for second time loses options settings
        # so reset
        
        if opts:
            TvnzLoader.options = opts
        self.options_list = split_options(TvnzLoader.options)
        # direct download

        if 'http' in search_term and inx == 1:

            if self.options_list[0] == '':
                command = ['devine', 'dl', 'TVNZ', search_term]
            else:
                command = ['devine', 'dl', *self.options_list, 'TVNZ', search_term]    
            subprocess.run(command)
            
            
            return

        # keyword search
        elif inx == 3:
            print(f"Searching for {search_term}")
            return (self.fetch_videos(search_term))  
        
        #  POP-UP MENU alternates:  
        elif inx == 0:  
            # from greedy-search OR selecting Browse-category
            # need a search keyword(s) from url 
            # split and select series name
            search_term = search_term.split('/')[4] 

            return (self.fetch_videos(search_term))
        
        elif 'http' in search_term and inx == 2:
            self.category = category
            self.fetch_videos_by_category(search_term)  # search_term here holds a URL!!!
            
        else:
            print(f"Unknown error when searching for {search_term}")

        return
    def fetch_videos(self, search_term):
        """Fetch videos from Channel 4 using a search term.
            Here the first search for series titles matches all or part of search_term.
            The function will prepare the series data, matching the search term for display.
        """
        # returns json as type String
        url = f"https://apis-public-prod.tech.tvnz.co.nz/api/v1/web/play/search?q={search_term}"
        try:
            html = self.get_data(url)
            if 'No Matches' in html:
                print('Nothing found for that search; try again.')
                return
            else:
                parsed_data = self.parse_data(html)  # to json
        except Exception:
            print(f'No valid data returned for {url}')
            return
        #console.print_json(data=parsed_data)
        f = open('tvnz.json', 'w')
        f.write(json.dumps(parsed_data))  # parsed_data)
        f.close()
        if parsed_data and 'results' in parsed_data:
            for item in parsed_data['results']:
                series_name = item.get('title', 'Unknown Series')
                url = 'https://apis-edge-prod.tech.tvnz.co.nz' + item.get('page', {}).get('href', '')
                episode = {
                    'type': item.get('type'),  # 'type'
                    'title': item.get('title', 'Unknown Title'),
                    'url': url,
                    'synopsis': item.get('synopsis','No synopsis available.')
                }
                self.add_episode(series_name, episode)
        else:
            print(f'No valid data returned for {url}')
            return None
        selected_series = self.display_series_list()
        if selected_series:
            return self.second_fetch(selected_series)  # Return URLs for selected episodes
        return None


    def second_fetch(self, selected):
        # TVNZ video type: sportVideo, showVideo or Movie
        # makes this extractor unusual and should not be used 
        # to model other services
        """
        Given a selected series name, fetch its HTML and extract its episodes.
        Or if given a direct url, fetch it and process for greedy download.
        The function will prepare the series data for episode selection and display the final episode list.
        It will return the URLs for the selected episodes.
        """
        if 'https' in selected:  # direct url provided skip url preparation
            url = selected
        else:
            #initial pass to find type
            series_name = selected.lower().replace(' ', '-').replace(':','').replace(",",'') 
            episodes = self.get_series_data()
            episode_test = episodes[selected][0]
            type = episode_test.get('type')
            beaupylist = []
            # if sport video - assume no episodes
            # use data from first fetch directly
            if type == 'sportVideo':
                for item in episodes[selected]:  # existing data
                    url = 'https://www.tvnz.co.nz/' + item.get('url').split('/page/')[1]
                    beaupylist.append(f"{item.get('title')} {url}\n\t{item.get('synopsis', 'No synopsis available.')}")

                selected = select_multiple(beaupylist, preprocessor=lambda val: prettify(val),  minimal_count=1, cursor_style="pink1" ,pagination=True, page_size = 8)

                for item in selected:
                    url = item.split(' ')[-1].split('\n\t')[0]
                    if self.options_list[0] == '':
                        command = ['devine', 'dl', 'TVNZ', url]
                    else:
                        command = ['devine', 'dl', *self.options_list, 'TVNZ', url]
                    subprocess.run(command)
                return None

            elif type == 'show' or type == 'showVideo':
                url = f'https://apis-public-prod.tech.tvnz.co.nz/api/v1/web/play/page/shows/{series_name}/episodes' 
                try:
                    html = self.get_data(url)
                    parsed_data = self.parse_data(html)
                except Exception:

                    try:
                        # direct download as seems only one episode
                        # https://www.tvnz.co.nz/shows/circle-of-friends/movie/s1-e1
                        url = f'https://www.tvnz.co.nz/shows/{series_name}/movie/s1-e1'
                        if self.options_list[0] == '':
                            command = ['devine', 'dl', 'TVNZ', url]
                        else:
                            command = ['devine', 'dl', *self.options_list, 'TVNZ', url]
                        subprocess.run(command) 
                        return
                    
                    except Exception:
                        print(f'No valid data returned for {url}')
                        return
                try:  
                    #html = self.get_data(url)
                    #parsed_data = self.parse_data(html)
                    
                    href_list = []
                    
                    # iterate over all seasons and capture url for each
                    for item in parsed_data['layout']['slots']['main']['modules'][0]['lists']:
                        href_list.append(item['href'])
                except Exception:
                    print(f'No valid data returned for {url}')
                    return
        # with season url, iterate over each season and capture episodes   
        try:
            for url in href_list:  #  for all seasons
                url = 'https://apis-edge-prod.tech.tvnz.co.nz' + url
                myhtml = self.get_data(url=url)
                parsed_data = self.parse_data(myhtml)
                if parsed_data and '_embedded' in parsed_data:
                    try:
                        for item_key, item in parsed_data['_embedded'].items():
                            series_no = item.get('seasonNumber', '100')
                            myurl = 'https://tvnz.co.nz' + item.get('page', {}).get('url', '')
                            episode_no = item.get('episodeNumber', None)
                            synopsis = item.get('synopsis', 'No synopsis available')
                            episode = {
                                'series_no': series_no,
                                'title': episode_no,
                                'url': myurl,
                                'synopsis': synopsis
                            }
                            self.add_episode(series_name, episode)
                    except Exception:
                        pass  

                else:
                    print(f"No valid data at {url} found.\n Exiting")
                    return
        except Exception:
            print(f'No valid data returned for {url}')
            return
        
        self.options_list = split_options(self.options)

        if self.get_number_of_episodes(series_name) == 1:
            item = self.get_series(series_name)[0]
            url = "https://tvnz.co.nz" + item['url']
            
            if self.options_list[0] == '':
                command = ['devine', 'dl', 'TVNZ', url]
            else:
                command = ['devine', 'dl', *self.options_list, 'TVNZ', url]
            subprocess.run(command)
            return None
        
        self.prepare_series_for_episode_selection(series_name) # creates list of series; allows user selection of wanted series prepares an episode list over chosen series
        self.final_episode_data = self.sort_episodes(self.get_final_episode_list())
        selected_final_episodes = self.display_final_episode_list(self.final_episode_data)

        for item in selected_final_episodes:
            url = item.split(',')[2].lstrip()

            if url  == 'None':
                print(f"No valid URL for {item.split(',')[1]}")
                continue
            
            if self.options_list[0] == '':
                command = ['devine', 'dl', 'TVNZ', url]
            else:
                command = ['devine', 'dl', *self.options_list, 'TVNZ', url]
            subprocess.run(command)
            
            return
        
    def fetch_videos_by_category(self, browse_url):
        """
        Fetches videos from a category (Channel 4 specific).
        Args:
            browse_url (str): URL of the category page.
        Returns:
            None
        """
        
        try:
            req = self.get_data(browse_url, headers=self.headers)
            
            # Parse the __PARAMS__ data 
            parsed_data = self.parse_data(req)

            '''console.print_json(data=parsed_data)
            f = open("cat_tvnz.json",'w')
            f.write(json.dumps(parsed_data))
            f.close()'''
            i = 1
            beaupylist = []
            linkList = []
           
            for item_key, item in parsed_data['_embedded'].items():
                print(item_key)
                try:
                    if item.get('type') == 'category':
                        continue
                    elif item.get('type') == 'showVideo': 
                        myurl = 'https://tvnz.co.nz' + item.get('page', {}).get('url', '')
                        showType = item.get('showType', 'unknown')
                    elif item.get('type') == 'show':
                        showType = item.get('showType', 'unknown')
                        myurl = 'https://tvnz.co.nz' + item.get('watchAction', {}).get('link', '')
                    elif item.get('type') == 'sportVideo':
                        showType = item.get('showType', 'unknown')
                        myurl = 'https://tvnz.co.nz' + item.get('page', {}).get('url', '')
                        print(myurl)

                    synopsis = item.get('synopsis', 'No synopsis available')
                    title = item.get('title', 'unknown')
                    beaupylist.append(f"{i} {title.replace('_',' ')}\n\t{synopsis}") 
                    linkList.append([myurl, showType])  
                    i += 1
                except:
                    continue       
        except Exception as e:
                print(f"Error fetching category data: {e}")
                return      
               
        # call function in BaseLoader

        found = self.display_beaupylist(beaupylist)
        
        if found:
            ind = found.split(' ')[0]
            url, showType = linkList[int(ind)-1]
            if showType == 'Movie':
                # direct download
                return self.receive(inx=1, search_term=url)
            elif showType == 'sportVideo':
                self.showType = showType
                # tring to catch sports videos
                #
                #
                #

            else:
                # greedy search
                search_term = url.split('/')[4].replace('-',' ')
                return self.receive(inx=3, search_term=search_term)
        else:
            print("No video selected.")
            return