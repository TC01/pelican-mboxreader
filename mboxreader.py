from pelican import signals
from pelican.generators import ArticlesGenerator

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

		for message in mbox.itervalues():
			author = message['from']
			subject = message['subject']
			strdate = message['date']
			content = message.get_payload()

def get_generators(pelican_object):
	return MboxGenerator

signals.get_generators.connect(get_generators)
