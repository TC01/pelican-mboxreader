from pelican import signals
from pelican.generators import ArticlesGenerator, Generator
from pelican.contents import Article, Page, Static, is_valid_content
from pelican.utils import copy, process_translations, mkdir_p, DateFormatter, slugify
from pelican.readers import BaseReader, Readers

from pelican import signals

from itertools import chain, groupby
from operator import attrgetter, itemgetter
from collections import defaultdict
from functools import partial

import datetime
import mailbox
import logging
import os
import pytz

# Other dependency! dateutil.
try:
	from dateutil import parser
except ImportError:	#NOQA?
	parser = False

# Markdown-- a half-decent plaintext -> HTML converter, for now.
try:
    from markdown import Markdown
except ImportError:
    Markdown = False  # NOQA

# The logger.
logger = logging.getLogger()

# Settings methods, adapted from tag-cloud plugin.
# https://github.com/getpelican/pelican-plugins/blob/master/tag_cloud/tag_cloud.py
def set_default_settings(settings):
	settings.setdefault('MBOX_PATH', '[input.mbox]')
	settings.setdefault('MBOX_CATEGORY', '[Mailbox]')
	settings.setdefault('MBOX_AUTHOR_STRING', 'via email')
	settings.setdefault('MBOX_MARKDOWNIFY', False)

def init_default_config(pelican):
	from pelican.settings import DEFAULT_CONFIG
	set_default_settings(DEFAULT_CONFIG)
	if pelican:
		set_default_settings(pelican.settings)

def plaintext_to_html(plaintext, markdownify=False):
	# Attempt to use markdown as a basic plaintext -> HTML converter, if told to do so.
	# If we fail, or were *not* told to do so, insert <p> tags as appropriate.
	try:
		if not markdownify:
			raise RuntimeError
		content = Markdown().convert(plaintext)
	except:
		content = ''
		plaintext = plaintext.replace('\r\n', '\n')
		strings = plaintext.split('\n\n')
		for paragraph in strings:
			paragraph = paragraph.replace('\n', '<br/>')
			content += '<p>' + paragraph + '</p>\n\n'
		
	return content

class MboxGenerator(ArticlesGenerator):

	def __init__(self, *args, **kwargs):
		"""initialize properties"""
		self.articles = []  # only articles in default language
		self.translations = []
		self.dates = {}
		self.categories = defaultdict(list)
		self.authors = defaultdict(list)
		super(MboxGenerator, self).__init__(*args, **kwargs)

	# Private helper function to generate 
	def _generate_mbox_articles(self, mboxPath, mboxCategory):
		
		category = BaseReader(self.settings).process_metadata('category', mboxCategory)
		
		# Complain if the mbox path does not exist and is not readable.
		try:
			if not os.path.exists(mboxPath):
				raise RuntimeError
			mbox = mailbox.mbox(mboxPath)
		except:
			logger.error('Could not process mbox file %s', mboxPath)
			return
		
		# Loop over all messages in the mbox and turn them into an article object.
		all_articles = []
		slugs = []
		
		for message in mbox.itervalues():
			# Get author name.
			author = message['from']
			if author is None:
				author = 'Unknown'
			else:
				if '<' and '>' in author:
					author = author[:author.find(' <')]
				author = author.replace('"', '').replace("'", '')
			# As a hack to avoid dealing with the fact that names can collide.
			author += ' ' + self.settings.get('MBOX_AUTHOR_STRING')
			authorObject = BaseReader(self.settings).process_metadata('author', author)

			# Get date object, using python-dateutil as an easy hack.
			# If there is no date in the message, abort, we shouldn't bother.
			if message['date'] is None:
				continue
			if parser:
				date = parser.parse(message['date'])
			else:
				logger.error('No python-dateutil, we cannot continue as date formats cannot be parsed. ')
				continue
			monthYear = date.strftime('%B-%Y').lower()

			# Get title and slug; build year + month into slug.
			subject = message['subject']
			slug = os.path.join(slugify(mboxCategory), monthYear, slugify(subject))

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

			# Code adapted from Stackoverflow for parsing email messages.
			# https://stackoverflow.com/questions/4824376/parse-multi-part-email-with-sub-parts-using-python
			# Code is clumsy, should be refactored.
			if message.is_multipart():
				plaintext = None
				html = None
				for part in message.get_payload():
					charset = message.get_content_charset()
					if charset is None or charset == 'x-unknown':
						charset = 'us-ascii'
					if part.get_content_type() == 'text/plain':
						plaintext = unicode(part.get_payload(decode=True), charset, "ignore").encode('ascii', 'replace')
					if part.get_content_type() == 'text/html':
						html = unicode(part.get_payload(decode=True), charset, "ignore").encode('ascii', 'replace')
				if plaintext is None and html is None:
					continue
				elif plaintext is None:
					content = html
				else:
					content = plaintext_to_html(plaintext, self.settings.get('MBOX_MARKDOWNIFY'))
			else:
				charset = message.get_content_charset()
				if charset is None or charset == 'x-unknown':
					charset = 'us-ascii'
				plaintext = unicode(message.get_payload(decode=True), charset, "ignore").encode('ascii', 'replace')
				content = plaintext_to_html(plaintext, self.settings.get('MBOX_MARKDOWNIFY'))
			
			metadata = {'title':subject, 'date':date, 'category':category, 'authors':[authorObject], 'slug':slug}
			article = Article(content=content, metadata=metadata, settings=self.settings, source_path=mboxPath, context=self.context)

			# This seems like it cannot happen... but it does without fail. 3.3?
			article.author = article.authors[0]
			all_articles.append(article)

		return all_articles
		

	# For now, don't generate feeds.
	def generate_feeds(self, writer):
		return

	def generate_pages(self, writer):
		"""Generate the pages on the disk"""
		write = partial(writer.write_file, relative_urls=self.settings['RELATIVE_URLS'], override_output=True)

		# to minimize the number of relative path stuff modification
		# in writer, articles pass first
		self.generate_articles(write)
		self.generate_period_archives(write)
		self.generate_direct_templates(write)

		# and subfolders after that
		self.generate_categories(write)
		self.generate_authors(write)

	def generate_articles(self, write):
		"""Generate the articles."""
		# Hm... this is a bit clunky; it overrides the override_output setting.
		# Maybe that's not a problem; I'm not sure how else to do it and I think it's okay.
		for article in chain(self.translations, self.articles):
			write(article.save_as, self.get_template(article.template),
					self.context, article=article, category=article.category,
					override_output=True, blog=True)

	def generate_context(self):
		# Update the context.
		self.articles = self.context['articles']  # only articles in default language
		
		# Complain if MBOX_PATH and MBOX_CATEGORY are not of the same length, complain.
		mboxPaths = self.settings.get('MBOX_PATH')
		mboxCategories = self.settings.get('MBOX_CATEGORY')
		if len(mboxPaths) != len(mboxCategories) or len(mboxPaths) <= 0:
			logger.error('MBOX_PATH and MBOX_CATEGORY not of equal length or non-empty.')
			return
		
		all_articles = []
		for i in xrange(len(mboxPaths)):
			mboxPath = mboxPaths[i]
			mboxCategory = mboxCategories[i]			

			new_articles = self._generate_mbox_articles(mboxPath, mboxCategory)
			all_articles.extend(new_articles)

			# Log that we did stuff.
			print('Read in %d messages from %s and converted to articles in category %s.' % (len(new_articles), mboxPath, mboxCategory))
		print('Read in %d messages from mailboxes total.' % (len(all_articles)))

		# Continue with the rest of ArticleGenerator.
		# Code adapted from https://github.com/getpelican/pelican/blob/master/pelican/generators.py#L548

		# ARTICLE_ORDER_BY doesn't exist in 3.3, yay Fedora 21 package maintainers.
		articles, translations = process_translations(all_articles)#, order_by=self.settings['ARTICLE_ORDER_BY'])
		self.articles.extend(articles)
		self.translations.extend(translations)

		# Disabled for 3.3 compatibility, great.
		#signals.article_generator_pretaxonomy.send(self)

		for article in self.articles:
			# only main articles are listed in categories and tags
			# not translations
			# We have to use django for this, unfortunately.
			if article.date.tzinfo is None:
				article.date = pytz.UTC.localize(article.date)
			self.categories[article.category].append(article)
			for author in getattr(article, 'authors', []):
				self.authors[author].append(article)

		# This may not technically be right, but... sort the articles by date too.
		self.articles = list(self.articles)
		self.dates = self.articles
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
		#signals.article_generator_finalized.send(self)

def get_generators(pelican_object):
	return MboxGenerator

def register():
	signals.initialized.connect(init_default_config)
	signals.get_generators.connect(get_generators)
