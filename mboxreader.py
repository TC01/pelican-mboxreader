from pelican import signals
from pelican.generators import ArticlesGenerator
from pelican.contents import Article

import mailbox

# For now hardcode this.
mboxPath = '/home/bjr/Programming/python/pelican/security.mbox'

class MboxGenerator(ArticlesGenerator):

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
		for message in mbox.itervalues():
			author = message['from']
			subject = message['subject']
			# This is a bad hack for mailman formatting, we should probably use mbox name by default.
			# Or, make it configurable. Yay configuration.
			category = subject[subject.find(']') + 2:]
			strdate = message['date']
			content = message.get_payload()

			metadata = {'title':subject, 'date':strdate, 'category':category)
			article = Article(content=content, metadata=metadata, settings=self.settings, source_path=None, context=self)
			all_articles.append(article)

		# Continue with the rest of ArticleGenerator.
		# Code adapted from https://github.com/getpelican/pelican/blob/master/pelican/generators.py#L548

		# And finish.
		signals.article_generator_finalized.send(self)

def get_generators(pelican_object):
	return MboxGenerator

signals.get_generators.connect(get_generators)
