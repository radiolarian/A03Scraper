######
#
# This script takes in (a list or csv of) fic IDs and
# writes a csv containing the fic itself, as well as the 
# metadata.
#
# Usage - python ao3_get_fanfics.py ID [--header header] [--csv csvoutfilename] 
#
# ID is a required argument. It is either a single number, 
# multiple numbers seperated by spaces, or a csv filename where
# the IDs are the first column.
# (It is suggested you run ao3_work_ids.py first to get this csv.)
#
# --header is an optional string which specifies your HTTP header
# for ethical scraping. For example, the author's would be 
# 'Chrome/52 (Macintosh; Intel Mac OS X 10_10_5); Jingyi Li/UC Berkeley/email@address.com'
# If left blank, no header will be sent with your GET requests.
# 
# --csv is an optional string which specifies the name of your
# csv output file. If left blank, it will be called "fanfics.csv"
# Note that by default, the script appends to existing csvs instead of overwriting them.
# 
# --restart is an optional string which when used in combination with a csv input will start
# the scraping from the given work_id, skipping all previous rows in the csv
#
# --bookmarks is an optional flag which collects the users who have bookmarked a fic.  
# Because this is a slow operation, it is excluded by default. 
#
# Author: Jingyi Li soundtracknoon [at] gmail
# I wrote this in Python 2.7. 9/23/16
# Updated 2/13/18 (also Python3 compatible)
#######
import requests
from bs4 import BeautifulSoup
import argparse
import time
import os
import csv
import sys
from unidecode import unidecode

# seconds to wait between page requests
delay = 5

def get_tag_info(category, meta):
	'''
	given a category and a 'work meta group, returns a list of tags (eg, 'rating' -> 'explicit')
	'''
	try:
		tag_list = meta.find("dd", class_=str(category) + ' tags').find_all(class_="tag")
	except AttributeError as e:
		return []
	return [unidecode(result.text) for result in tag_list] 
	
def get_stats(meta):
	'''
	returns a list of  
	language, published, status, date status, words, chapters, comments, kudos, bookmarks, hits
	'''
	categories = ['language', 'published', 'status', 'words', 'chapters', 'comments', 'kudos', 'bookmarks', 'hits'] 

	stats = list(map(lambda category: meta.find("dd", class_=category), categories))

	if not stats[2]:
		stats[2] = stats[1] #no explicit completed field -- one shot
	try:		
		stats = [unidecode(stat.text) for stat in stats]
	except AttributeError as e: #for some reason, AO3 sometimes miss stat tags (like hits)
		new_stats = []
		for stat in stats:
			if stat: new_stats.append(unidecode(stat.text))
			else: new_stats.append('null')
		stats = new_stats

	stats[0] = stats[0].rstrip().lstrip() #language has weird whitespace characters
	#add a custom completed/updated field
	status  = meta.find("dt", class_="status")
	if not status: status = 'Completed' 
	else: status = status.text.strip(':')
	stats.insert(2, status)

	return stats      

def get_tags(meta):
	'''
	returns a list of lists, of
	rating, category, fandom, pairing, characters, additional_tags
	'''
	tags = ['rating', 'category', 'fandom', 'relationship', 'character', 'freeform']
	return list(map(lambda tag: get_tag_info(tag, meta), tags))

# get kudos
def get_all_kudos(url, header_info):
	headers = {'user-agent' : header_info}
	all_kudos = []

	req = requests.get(url, headers=headers)
	src = req.text
	soup = BeautifulSoup(src, 'html.parser')

	# find all pages
	if (soup.find('ol', class_='pagination actions')):
		pages = soup.find('ol', class_='pagination actions').findChildren("li" , recursive=False)
		max_pages = int(pages[-2].contents[0].contents[0])
		count = 1

		while count <= max_pages:
			print ('count', count)
			# extract each bookmark per user
			tags = soup.find("p", class_="kudos")
			all_kudos += get_users(tags, 'kudo')

			# next page
			count+=1
			req = requests.get(url+'?page='+str(count), headers=headers)
			src = req.text
			soup = BeautifulSoup(src, 'html.parser')
	else:
		# single page of kudos
		tags = soup.find("p", class_="kudos")
		all_kudos += get_users(tags, 'kudo')
		
	return all_kudos

# get author(s)
def get_authors(meta):
	tags = meta.contents
	authors = []

	for tag in tags:
		if tag.name == 'a':
			authors.append(tag.contents[0])

	return authors

# get bookmarks by page
def get_bookmarks(url, header_info):
	bookmarks = []
	headers = {'user-agent' : header_info}

	req = requests.get(url, headers=headers)
	src = req.text

	time.sleep(delay)
	soup = BeautifulSoup(src, 'html.parser')

	sys.stdout.write('scraping bookmarks ')
	sys.stdout.flush()

	# find all pages
	if (soup.find('ol', class_='pagination actions')):
		pages = soup.find('ol', class_='pagination actions').findChildren("li" , recursive=False)
		max_pages = int(pages[-2].contents[0].contents[0])
		count = 1
	
		sys.stdout.write('(' + str(max_pages) + ' pages)')
		sys.stdout.flush()

		while count <= max_pages:
			# extract each bookmark per user
			tags = soup.findAll('li', class_='user short blurb group')
			bookmarks += get_users(tags, 'bookmark')

			# next page
			count+=1
			req = requests.get(url+'?page='+str(count), headers=headers)
			src = req.text
			soup = BeautifulSoup(src, 'html.parser')
			sys.stdout.write('.')
			sys.stdout.flush()
			time.sleep(delay)
	else:
		tags = soup.findAll('li', class_='user short blurb group')
		bookmarks += get_users(tags, 'bookmark')

	print('')
	return bookmarks

# get users from bookmarks/kudos
def get_users (meta, kind):
	users = []

	if meta != None:
		for tag in meta:
				if type(tag).__name__ == 'Tag':
					if kind == 'kudo':
						user = tag.contents[0]
					elif kind == 'bookmark':
						username = tag.find('h5', class_='byline heading').findChildren('a')[0].contents[0]
						datetime = tag.findChildren('p', class_='datetime')[0].contents[0]

						bookmarkTags = tag.findAll('a', class_='tag')
						bookmarkTags = [item.contents[0] for item in bookmarkTags]

						collections = tag.find('ul', class_='meta commas')
						if collections != None:
							collections = [item.contents[0] for item in collections.findAll('a')]
						
						summary = tag.find('blockquote', class_='userstuff summary')
						if summary != None: 
							summary = summary.findAll('p')
							summary = [item.contents[0] for item in summary]

						user = { 'username': username, 'date': datetime, 'tags': bookmarkTags, \
							'collections': collections, 'summary': summary}

					users.append(user)

	return users

def get_single_comment(comment, parent):
	# Find username
	if comment.find('h4', class_='heading byline').find('a'):
		username = comment.find('h4', class_='heading byline').find('a').contents[0]
	else:
		username = comment.find('h4', class_='heading byline').contents[0]

	# Get datetime
	datetime = comment.find('h4', class_='heading byline').find('span', class_="posted datetime").contents
	remove = ['\n', ' ']
	dateObj = {}

	for item in datetime:
		if item not in remove:
			itemClass = item['class'][0]
			itemValue = item.contents[0]
			dateObj[itemClass] = itemValue

	# Get comment id
	commentid = comment['id'].split('_')[1]

	# Get direct comment text
	text = comment.find('blockquote', class_ ='userstuff')#.findAll('p').contents[0]
	text = text.findAll('p')
	text = [item.contents[0] for item in text]
	fullText = ''

	for i, item in enumerate(text):
		if i < len(text) - 1:
			fullText += item + '\n'
		else:
			fullText += item

	# Create object and return
	commentData = {'user': username, 'datetime': dateObj, 'id': commentid, 'parent': parent, 'text': fullText}
	return commentData

def get_comment_thread(comment_thread, parent):
	all_comments = []

	# Recurse till you find the deepest level
	try:
		nest_level = comment_thread[0]
		nest_level = nest_level.findChild('ol', class_ ='thread')[0]

		new_comments = get_comment_thread(comment_thread, False)
		all_comments.append(new_comments)
	except:
		# you've found the deepest level
		comments = comment_thread[0].find_all('li')
		all_comments = []

		# extracts all comments in line thread
		for c, comment in enumerate(comments):
				try:
					if comment.attrs['class']:
						if 'odd' in comment.attrs['class'] or 'even' in comment.attrs['class']:
							single_comment = get_single_comment(comment, False)
							all_comments.append(single_comment)
							
				except:
					pass
    
		return all_comments

	return all_comments

def get_comments(url, header_info):
	all_comments = []
	headers = {'user-agent' : header_info}

	req = requests.get(url, headers=headers)
	src = req.text
	soup = BeautifulSoup(src, 'html.parser')

	# find all pages
	if (soup.find('ol', class_='pagination actions')):
		pages = soup.find('ol', class_='pagination actions').findChildren("li" , recursive=False)
		max_pages = int(pages[-2].contents[0].contents[0])
		count = 1

		while count <= max_pages:
			comments = soup.find('ol', class_ = 'thread').findChildren("li" , recursive=False)

			# comments processing
			for c, comment in enumerate(comments):
				try:
					if comment.attrs['class']:
						if 'odd' in comment.attrs['class'] or 'even' in comment.attrs['class']:
							single_comment = get_single_comment(comment, True)
							all_comments.append(single_comment)

				# likely a comment thread
				except:
					if comment.findChild('ol', class_="thread"):
						all_comments.append(get_comment_thread(comment.findChildren('ol'), True, all_comments))

			# next page
			count+=1
			req = requests.get(url+'?page='+str(count), headers=headers)
			src = req.text
			soup = BeautifulSoup(src, 'html.parser')
			
	else:
		comments = soup.find('ol', class_ = 'thread').findChildren("li" , recursive=False)
		last_count = 0

		# comments processing
		for c, comment in enumerate(comments):
			try:
				if comment.attrs['class']:
					if 'odd' in comment.attrs['class'] or 'even' in comment.attrs['class']:
						single_comment = get_single_comment(comment, True)
						all_comments.append(single_comment)
						last_count+=1

			# likely a comment thread
			except:
				if comment.findChild('ol', class_="thread"):
					if len(all_comments) > 0:
						new_comments = get_comment_thread(comment.findChildren('ol'), True)
						
						# If it's a bunch of replies, store as reply to previous comment
						if len(all_comments) == last_count:
							all_comments[-1]['reply'] = new_comments
							last_count+=1 # To move the index along so that you don't erase the comments
						else:
							all_comments.append(new_comments)
					else:
						new_comments = get_comment_thread(comment.findChildren('ol'), True)
						all_comments.append(new_comments)
						last_count +=1

	return all_comments
	
def access_denied(soup):
	if (soup.find(class_="flash error")):
		return True
	if (not soup.find(class_="work meta group")):
		return True
	return False

def write_fic_to_csv(fic_id, only_first_chap, lang, include_bookmarks, writer, errorwriter, header_info=''):
	'''
	fic_id is the AO3 ID of a fic, found every URL /works/[id].
	writer is a csv writer object
	the output of this program is a row in the CSV file containing all metadata 
	and the fic content itself.
	header_info should be the header info to encourage ethical scraping.
	'''
	print('Scraping ', fic_id)
	url = 'http://archiveofourown.org/works/'+str(fic_id)+'?view_adult=true'
	if not only_first_chap:
		url = url + '&amp;view_full_work=true'
	headers = {'user-agent' : header_info}
	req = requests.get(url, headers=headers)
	src = req.text
	soup = BeautifulSoup(src, 'html.parser')

	print (url)
	if (access_denied(soup)):
		print('Access Denied')
		error_row = [fic_id] + ['Access Denied']
		errorwriter.writerow(error_row)
	else:
		meta = soup.find("dl", class_="work meta group")
		author = get_authors(soup.find("h3", class_="byline heading"))
		tags = get_tags(meta)
		stats = get_stats(meta)
		title = unidecode(soup.find("h2", class_="title heading").string).strip()

		#get kudos
		kudos_url = 'http://archiveofourown.org' + soup.find(id='kudos_more_link')['href']

		all_kudos = get_all_kudos(kudos_url, header_info)
		
		#get bookmarks
		bookmark_url = 'http://archiveofourown.org/works/'+str(fic_id)+'/bookmarks'
		all_bookmarks = get_bookmarks(bookmark_url, header_info)

		# get comments
		comments_url  = 'http://archiveofourown.org/works/' + str(fic_id) + '?show_comments=true#comments'
		all_comments = get_comments(comments_url, header_info)

		#get the fic itself
		content = soup.find("div", id= "chapters")
		chapters = content.select('p')
		chaptertext = '\n\n'.join([unidecode(chapter.text) for chapter in chapters])

		row = [fic_id] + [title] + [author] + list(map(lambda x: ', '.join(x), tags)) + stats + [all_kudos] + [all_bookmarks] + [all_comments] + [chaptertext]

		try:
			writer.writerow(row)
		except:
			print('Unexpected error: ', sys.exc_info()[0])
			error_row = [fic_id] +  [sys.exc_info()[0]]
			errorwriter.writerow(error_row)
		print('Done.')

def get_args(): 
	parser = argparse.ArgumentParser(description='Scrape and save some fanfic, given their AO3 IDs.')
	parser.add_argument(
		'ids', metavar='IDS', nargs='+',
		help='a single id, a space seperated list of ids, or a csv input filename')
	parser.add_argument(
		'--csv', default='fanfics.csv',
		help='csv output file name')
	parser.add_argument(
		'--header', default='',
		help='user http header')
	parser.add_argument(
		'--restart', default='', 
		help='work_id to start at from within a csv')
	parser.add_argument(
		'--firstchap', default='', 
		help='only retrieve first chapter of multichapter fics')
	parser.add_argument(
		'--lang', default='', 
		help='only retrieves fics of certain language (e.g English), make sure you use correct spelling and capitalization or this argument will not work')
	parser.add_argument(
		'--bookmarks', action='store_true', 
		help='retrieve bookmarks; ')
	args = parser.parse_args()
	fic_ids = args.ids
	is_csv = (len(fic_ids) == 1 and '.csv' in fic_ids[0]) 
	csv_out = str(args.csv)
	headers = str(args.header)
	restart = str(args.restart)
	ofc = str(args.firstchap)
	lang = str(args.lang)
	include_bookmarks = args.bookmarks
	if ofc != "":
		ofc = True
	else:
		ofc = False
	if lang == "":
		lang = False
	return fic_ids, csv_out, headers, restart, is_csv, ofc, lang, include_bookmarks

def process_id(fic_id, restart, found):
	if found:
		return True
	if fic_id == restart:
		return True
	else:
		return False

def main():
	fic_ids, csv_out, headers, restart, is_csv, only_first_chap, lang, include_bookmarks = get_args()
	os.chdir(os.getcwd())
	with open(csv_out, 'a') as f_out:
		writer = csv.writer(f_out)
		with open("errors_" + csv_out, 'a') as e_out:
			errorwriter = csv.writer(e_out)
			#does the csv already exist? if not, let's write a header row.
			if os.stat(csv_out).st_size == 0:
				print('Writing a header row for the csv.')
				header = ['work_id', 'title', 'author', 'rating', 'category', 'fandom', 'relationship', 'character', 'additional tags', 'language', 'published', 'status', 'status date', 'words', 'chapters', 'comments', 'kudos', 'bookmarks', 'hits', 'all_kudos', 'all_bookmarks', 'all_comments', 'body']
				writer.writerow(header)
			if is_csv:
				csv_fname = fic_ids[0]
				with open(csv_fname, 'r+') as f_in:
					reader = csv.reader(f_in)
					if restart == '':
						for row in reader:
							if not row:
								continue
							write_fic_to_csv(row[0], only_first_chap, lang, include_bookmarks, writer, errorwriter, headers)
							time.sleep(delay)
					else: 
						found_restart = False
						for row in reader:
							if not row:
								continue
							found_restart = process_id(row[0], restart, found_restart)
							if found_restart:
								write_fic_to_csv(row[0], only_first_chap, lang, include_bookmarks, writer, errorwriter, headers)
								time.sleep(delay)
							else:
								print('Skipping already processed fic')

			else:
				for fic_id in fic_ids:
					write_fic_to_csv(fic_id, only_first_chap, lang, include_bookmarks, writer, errorwriter, headers)
					time.sleep(delay)

main()