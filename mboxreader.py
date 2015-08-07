from pelican import signals
from pelican.generators import ArticlesGenerator
from pelican.contents import Article, Page, Static, is_valid_content
from pelican.utils import copy, process_translations, mkdir_p, DateFormatter, slugify
from pelican.readers import BaseReader, Readers

from pelican import signals

from itertools import chain, groupby
from operator import attrgetter, itemgetter
from collections import defaultdict
from functools import partial

import mailbox
import logging
import os

# Other dependency! dateutil.
from dateutil import parser

# Markdown-- a half-decent plaintext -> HTML converter, for now.
try:
    from markdown import Markdown
except ImportError:
    Markdown = False  # NOQA

# Settings methods, adapted from tag-cloud plugin.
# https://github.com/getpelican/pelican-plugins/blob/master/tag_cloud/tag_cloud.py
def set_default_settings(settings):
	settings.setdefault('MBOX_PATH', 'input.mbox')
	settings.setdefault('MBOX_CATEGORY', 'Mailbox')
	settings.setdefault('MBOX_AUTHOR_STRING', 'via email')
	
def init_default_config(pelican):
	from pelican.settings import DEFAULT_CONFIG
	set_default_settings(DEFAULT_CONFIG)
	if pelican:
		set_default_settings(pelican.settings)

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
		
	def generate_pages(self, writer):
		"""Generate the pages on the disk"""
		write = partial(writer.write_file, relative_urls=self.settings['RELATIVE_URLS'])

		# to minimize the number of relative path stuff modification
		# in writer, articles pass first
		self.generate_articles(write)
		self.generate_period_archives(write)
		#self.generate_direct_templates(write)

		# and subfolders after that
		self.generate_categories(write)
		self.generate_authors(write)

	def generate_context(self):
		try:
			mbox = mailbox.mbox(self.settings.get('MBOX_PATH'))
		except:
			logger.error('Could not process mbox file %s', self.settings.get('MBOX_PATH'))
			# May not work properly.
			self._add_failed_source_path(self.settings.get('MBOX_PATH'))
			return

		category = BaseReader(self.settings).process_metadata('category', self.settings.get('MBOX_CATEGORY'))

		# Loop over all messages in the mbox and turn them into an article object.
		all_articles = []
		slugs = []
		for message in mbox.itervalues():
			# Get author name.
			author = message['from']
			author = author[:author.find(' <')]
			author = author.replace('"', '').replace("'", '')
			# As a hack to avoid dealing with the fact that names can collide.
			author += self.settings.get('MBOX_AUTHOR_STRING')
			authorObject = BaseReader(self.settings).process_metadata('author', author)
			
			# Get date object, using python-dateutil as an easy hack.
			date = parser.parse(message['date'])
			monthYear = date.strftime('%B_%Y')
			
			# Get title and slug; build year + month into slug.
			subject = message['subject']
			slug = os.path.join(monthYear, slugify(subject))
			
			# Hack to handle multiple messages with the same subject.
			if slug in slugs:
				slug += "_%d"
				count = 2
				testSlug = slug % count
				while testSlug in slugs:
					count += 1
					testSlug = slug % count
				slug = testSlug
			slugs.append(slug)

			content = Markdown().convert(message.get_payload())

			metadata = {'title':subject, 'date':date, 'category':category, 'authors':[authorObject], 'slug':slug}
			article = Article(content=content, metadata=metadata, settings=self.settings, source_path=self.settings.get('MBOX_PATH'), context=self.context)
			#article.content()
			# This seems like it cannot happen... but it does without fail. 3.3?
			article.author = article.authors[0]
			all_articles.append(article)

		# Continue with the rest of ArticleGenerator.
		# Code adapted from https://github.com/getpelican/pelican/blob/master/pelican/generators.py#L548

		# ARTICLE_ORDER_BY doesn't exist in 3.3, yay Fedora 21 package maintainers.
		self.articles, self.translations = process_translations(all_articles)#, order_by=self.settings['ARTICLE_ORDER_BY'])

		# Disabled for 3.3 compatibility, great.
		#signals.article_generator_pretaxonomy.send(self)

		for article in self.articles:
			# only main articles are listed in categories and tags
			# not translations
			self.categories[article.category].append(article)
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

		self._update_context(('articles', 'dates', 'categories', 'authors'))
		# Disabled for 3.3 compatibility for now, great.
		#self.save_cache()
		#self.readers.save_cache()

		# And finish.
		signals.article_generator_finalized.send(self)

def get_generators(pelican_object):
	return MboxGenerator

def register():
	signals.initialized.connect(init_default_config)
	signals.get_generators.connect(get_generators)