from datetime import datetime

from redlib.api.web import HtmlParser
from redlib.api.net import AbsUrl, RelUrl
from asq.initiators import query

from ...util.printer import printer
from ..base import SourceError, SourceParams, Source
from ..images import Images
from ..http_helper import HttpHelper
from ..html_helper import HtmlHelper
from ..trace import Trace
from ..image import Image


class XkcdParams(SourceParams):
	name = 'xkcd'

	def __init__(self, latest=False, query=None, year=None):
		self.query	= query
		self.year	= year
		self.latest	= latest

		self.hash_params = ['name']


class Xkcd(Source):
	name = 'xkcd'

	archive_url = 'http://xkcd.com/archive'
	base_url = 'http://xkcd.com'


	def __init__(self):
		self._trace = Trace()
		self._http = HttpHelper()

		self._latest_comic_image = None


	def get_image(self, params):
		self._params = params or XkcdParams()

		def select_latest():
			self._trace.add_step('latest comic', self._latest_comic_image.context_url)
			return self._latest_comic_image

		selector = select_latest if self._params.latest else None
		self._images = Images(self._params, cache=True, image_alias='comic', selector=selector, trace=self._trace)

		self._images.add_db_filter(lambda i, d : i.context_url is None or not d.seen_by_context_url(i.context_url))
		self._images.add_list_filter(lambda i, l : i.context_url is None or 
				len(query(l).where(lambda li : li.context_url == i.context_url).to_list()) == 0)
		self._images.add_select_filter(self.get_comic_image_url)

		if not self._images.available() or self._params.latest:
			self.scrape()

		return self._http.download_image(self._images, self._trace)


	def scrape(self):
		html_text = self._http.get(self.archive_url, msg='getting archive')

		html = HtmlHelper()
		etree = html.get_etree(html_text)

		links = etree.findall(".//div[@id='middleContainer']//a")

		cb = printer.printf('comics', '?', col_cb=True)
		c = 0
		for link in links:
			image = Image()

			image.context_url = self.base_url + (link.attrib.get('href') or html.parse_error('link href'))
			image.title = link.text
			date = link.attrib.get('title') or html.parse_error('link title')
			try:
				image.date = datetime.strptime(date, '%Y-%m-%d')
			except ValueError as e:
				html.parse_error(str(e))

			image.title += image.date.strftime(' (%d %b %Y)')
			self._images.add(image)

			if c == 0: self._latest_comic_image = image
			c += 1
			cb.col_cb(2, str(c))
		cb.col_update_cp()


	def get_comic_image_url(self, image):
		html_text = self._http.get(image.context_url, msg='getting comic page')

		html = HtmlHelper()
		etree = html.get_etree(html_text)

		imgs = etree.findall(".//div[@id='comic']/img")
		len(imgs) > 0 or html.parse_error('comic img')
		img = imgs[0]

		image.url = 'http:' + (img.attrib.get('src') or html.parse_error('comic img.src'))
		image.description = img.attrib.get('title')

		return image


	def get_trace(self):
		return self._trace.steps

