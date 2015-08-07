from pelican import signals
from pelican.generators import ArticlesGenerator
from pelican.contents import Article
from pelican.utils import process_translations

from operator import attrgetter
from collections import defaultdict

import mailbox

# Other dependency! dateutil.
from dateutil import parser

# For now hardcode this.
mboxPath = '/home/bjr/Programming/python/pelican/security.mbox'

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
			author = message['from']

			subject = message['subject']
			# Hack to handle multiple subjects.
			if subject in subjects:
				subject += "%d"
				count = 2
				testSubject = subject % count
				while testSubject in subjects:
					count += 1
					testSubject = subject % count
				subject = testSubject
			subjects.append(subject)

			# This is a bad hack for mailman formatting, we should probably use mbox name by default.
			# Or, make it configurable. Yay configuration.
			category = subject[subject.find(']') + 2:]

			date = parser.parse(message['date'])
			content = message.get_payload()

			metadata = {'title':subject, 'date':date, 'category':category}
			article = Article(content=content, metadata=metadata, settings=self.settings, source_path=None, context=self)
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

		self._update_context(('articles', 'dates', 'tags', 'categories', 'authors', 'related_posts'))
		# Disabled for 3.3 compatibility for now, great.
		#self.save_cache()
		#self.readers.save_cache()

		# And finish.
		signals.article_generator_finalized.send(self)

def get_generators(pelican_object):
	return MboxGenerator

def register():
	signals.get_generators.connect(get_generators)
