import shutil
import tempfile
from os.path import join as joinpath
from time import time
import os

from mutils.system import get_pictures_dir, prints
from mutils.image.imageinfo import get_image_info

from ..service import service_factory, ServiceError, IHttpService, IImageGenService
from ..util.retry import Retry
from ..util.logger import log
from .cwspec import CWSpec
from ..db import Image
from .. import web
from ..globals import Const
from ..desktop import desktop_factory, DesktopError
from .compute_wp_style import compute_wp_style
from ..server.protocol import WPState
from mayserver.transport.pipe_connection import PipeConnection
from ..db import func as dbfunc


class GetImageError(Exception):
	pass


class ChangeWPError(Exception):
	pass


class Client:
	def __init__(self, service_name=None, query=None, color=None, transport=None):
		self._service_name = service_name
		self._query = query
		self._color = color
		self._transport = transport


	def change_wallpaper(self):
		assert type(self._transport) == PipeConnection if self._transport is not None else True

		try:
			if self._transport is not None:
				self._transport.write_blocking(WPState.CHANGING)

			filepath, width, height = self.get_image()
			style = compute_style(width, height)

			dt = get_desktop()
			dt.set_wallpaper(filepath, style=style)

			dbfunc.set_last_change_time()

			if self._transport is not None:
				self._transport.write_blocking(WPState.READY)
				self._transport.write_blocking(filepath)
		
		except DesktopError as e:
			log.error('error while changing wallpaper')

		except GetImageError as e:
			log.error('error while getting image for wallpaper')
			if self._transport is not None:
				self._transport.write_blocking(WPState.ERROR)
			raise ChangeWPError()

		if is_py3(): print('')


	def get_image(self, spec):
		assert spec.__class__ == CWSpec

		retry = Retry(retries=3, final_exc=GetImageError())

		while retry.left():
			service = self.get_service(spec)
						
			try:
				temp_image_path, ext, image_url = self.get_image_to_temp_file(service, spec.query, spec.color)
				wp_path = self.move_temp_file(temp_image_path, ext)
				self.save_image_info(service, wp_path, image_url)

				retry.cancel()

			except ServiceError as e:
				log.error('unable to get image from %s'%spec.service_name)
				if spec.service_name is not None:
					retry.cancel()
				else:
					retry.retry()
				raise GetImageError()

		return wp_path, image.width, image.height


	def get_service(self, spec):
		if spec.service_name == None:
			service = service_factory.get_random()
		else:
			service = service_factory.get(spec.service_name)
			if service is None:
				log.error('%s: unknown service or service is disabled'%spec.service_name)
				raise GetImageError()

		prints('[%s]'%spec.service_name)
		log.debug('\n using %s..'%spec.service_name)

		return service


	def get_image_to_temp_file(self, service, query, color):
		image_url = None
		if IHttpService.providedBy(service):
			retry = Retry(retries=3, final_exc=ServiceError())
			while retry.left():
				image_url = service.get_image_url(query=query, color=color)
					
				ext = image.url[image_url.rfind('.') + 1 : ]
				fn, temp_image_path = tempfile.mkstemp()
				f = os.fdopen(fn, 'r+b')

				try:
					web.func.download(image.url, open_file=f)
					retry.cancel()

				except web.exc.TimeoutError as e:
					log.error(str(e))
					retry.retry()

				except web.exc.DownloadError as e:
					log.error(str(e))
					retry.retry()

				finally:
					f.close()

		elif IImageGenService.providedBy(service):
			temp_image_path = service.get_image(query=query, color=color)
			ext = service.get_extension()

		return temp_image_path, ext, image_url


	def move_temp_file(self, temp_path, ext):
		dirpath = get_pictures_dir() if not Const.debug else '.'
		wp_path = joinpath(dirpath, Const.wallpaper_basename + '.' + ext)

		try:
			shutil.move(temp_path, wp_path)
		except IOError as e:
			#handle move error, write to temp file error, disk full?
			log.error(str(e))
			raise GetImageError()

		return wp_path


	def save_image_info(self, service, wp_path, image_url):
		image = Image()

		image.url = image_url
		image.filepath = wp_path
		image.time = int(time())

		image.type, image.width, image.height = get_image_info(None, filepath=wp_path)
		image.size = os.stat(wp_path).st_size

		image_source = service.image_source
		image.description = image_source.description
		image.artist = image.artist

		add_trace(image.trace, service.image_trace)

		image.save()


	def add_trace(trace_list, steps):
		step = 1
		for trace_step in steps:
			trace_step.step = 0
			trace_list.append(trace_step)
			step += 1
