from pelican import signals
from pelican.generators import ArticlesGenerator
from pelican.contents import Article, Author
from pelican.utils import process_translations

from operator import attrgetter, itemgetter
from collections import defaultdict

import mailbox
import logging
import random

# Other dependency! dateutil.
from dateutil import parser

# Markdown-- a half-decent plaintext -> HTML converter, for now.
try:
    from markdown import Markdown
except ImportError:
    Markdown = False  # NOQA

# For now hardcode this.
mboxPath = '/home/bjr/Programming/python/pelican/security.mbox'
categoryName = 'Security'

class MboxGenerator(ArticlesGenerator):
	
	def __init__(self, *args, **kwargs):
		"""initialize properties"""
		self.articles = []  # only articles in default language
		self.translations = []
		self.dates = {}
		self.tags = defaultdict(list)
		self.categories = defaultdict(list)
		self.related_posts = []
		self.authors = defaultdict(list)
		super(MboxGenerator, self).__init__(*args, **kwargs)

	def generate_context(self):
		try:
			mbox = mailbox.mbox(mboxPath)
		except:
			logger.error('Could not process mbox file %s', mboxPath)
			# May not work properly.
			self._add_failed_source_path(mboxPath)
			return

		# Loop over all messages in the mbox and turn them into an article object.
		all_articles = []
		subjects = []
		for message in mbox.itervalues():
			# Get author name.
			author = message['from']
			author = author[:author.find(' <')]
			author = author.replace('"', '').replace("'", '')
			
			subject = message['subject']
			# Hack to handle multiple subjects.
			# This is bad because the subject is also the title; we should slugify the title first.
			if subject in subjects:
				subject += "%d"
				count = 2
				testSubject = subject % count
				while testSubject in subjects:
					count += 1
					testSubject = subject % count
				subject = testSubject
			subjects.append(subject)


			date = parser.parse(message['date'])
			content = Markdown().convert(message.get_payload())

			metadata = {'title':subject, 'date':date, 'category':categoryName, 'authors':[author]}
			article = Article(content=content, metadata=metadata, settings=self.settings, source_path=None, context=self)
			# This seems like it cannot happen... but it does without fail. 3.3?
			article.author = article.authors[0]
			all_articles.append(article)

		# Continue with the rest of ArticleGenerator.
		# Code adapted from https://github.com/getpelican/pelican/blob/master/pelican/generators.py#L548

		# ARTICLE_ORDER_BY doesn't exist in 3.3, yay Fedora 21 package maintainers.
		self.articles, self.translations = process_translations(all_articles)#, order_by=self.settings['ARTICLE_ORDER_BY'])

		# Disabled for 3.3 compatibility, great.
		#signals.article_generator_pretaxonomy.send(self)

		# Added for 3.3 compatibility.
		# create tag cloud
		tag_cloud = defaultdict(int)
		for article in self.articles:
			for tag in getattr(article, 'tags', []):
				tag_cloud[tag] += 1

		tag_cloud = sorted(tag_cloud.items(), key=itemgetter(1), reverse=True)
		tag_cloud = tag_cloud[:self.settings.get('TAG_CLOUD_MAX_ITEMS')]

		tags = list(map(itemgetter(1), tag_cloud))
		if tags:
			max_count = max(tags)
		steps = self.settings.get('TAG_CLOUD_STEPS')

		# calculate word sizes
		self.tag_cloud = [(tag, int(math.floor(steps - (steps - 1) * math.log(count) / (math.log(max_count) or 1)))) for tag, count in tag_cloud]
		# put words in chaos
		random.shuffle(self.tag_cloud)

		for article in self.articles:
			# only main articles are listed in categories and tags
			# not translations
			self.categories[article.category].append(article)
			if hasattr(article, 'tags'):
				for tag in article.tags:
					self.tags[tag].append(article)
			for author in getattr(article, 'authors', []):
				self.authors[author].append(article)

		self.dates = list(self.articles)
		self.dates.sort(key=attrgetter('date'), reverse=self.context['NEWEST_FIRST_ARCHIVES'])

		# and generate the output :)

		# order the categories per name
		self.categories = list(self.categories.items())
		self.categories.sort(reverse = self.settings['REVERSE_CATEGORY_ORDER'])

		self.authors = list(self.authors.items())
		self.authors.sort()

		self._update_context(('articles', 'dates', 'tags', 'categories', 'authors'))
		# Disabled for 3.3 compatibility for now, great.
		#self.save_cache()
		#self.readers.save_cache()

		# And finish.
		signals.article_generator_finalized.send(self)

def get_generators(pelican_object):
	return MboxGenerator

def register():
	signals.get_generators.connect(get_generators)
	pass