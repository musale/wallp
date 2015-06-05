from unittest import TestCase, main as ut_main, TestLoader
from functools import partial
from csv import reader

from wallp.db import Config, DBSession, Base, SettingError, Setting


def cmp_test_case_order(self, tc1, tc2):
	func1 = getattr(TestConfig, tc1)
	func2 = getattr(TestConfig, tc2)

	if getattr(func1, '__order__', None) is None or getattr(func2, '__order__', None) is None:
		return 0

	return func1.__order__ - func2.__order__

	
TestLoader.sortTestMethodsUsing = cmp_test_case_order


class SettingTestData:
	def __init__(self, fullname, value, vtype, valid_name, group, name, new_value, valid_new_value):
		self.fullname 		= fullname			#always str
		self.value 		= eval(value)			#str / int / float
		self.vtype 		= eval(vtype)			#str / int / float type
		self.valid_name 	= eval(valid_name)		#bool
		self.group 		= group				#always str
		self.name 		= name				#always str
		self.new_value 		= eval(new_value)		#str / int / float
		self.valid_new_value 	= eval(valid_new_value)		#bool


class TestConfig(TestCase):
	dbsession 		= None
	data_inserted 		= False
	settings 		= []
	db_path			= 'tc.db'
	test_data_csv_filepath	= 'test_config.csv'

	@classmethod
	def setUpClass(cls):
		cls.dbsession = DBSession(cls.db_path)
		Base.metadata.create_all(cls.dbsession.bind)
		cls.dbsession.commit()

		cls.load_test_data()


	@classmethod
	def load_test_data(cls):
		with open(cls.test_data_csv_filepath, 'r') as test_config_csv:
			test_config_csv.readline()
			test_config_csv.readline()
			test_data_reader = reader(test_config_csv)

			for row in test_data_reader:
				if row.count < 8:
					continue
				setting = SettingTestData(*[i.strip() for i in row[0 : 8]])
				cls.settings.append(setting)


	def insert_data(func, *args):
		'decorator for test cases'
		def new_func(*args):
			instance = args[0]
			assert type(instance) == TestConfig

			if instance.data_inserted:
				return

			config = Config()
			for setting in instance.settings:
				try:
					config.add(setting.fullname, setting.value, setting.vtype)
				except SettingError as e:
					continue
			instance.dbsession.commit()

			func(*args)

		return new_func


	def exe_order(order):
		'decorator for test cases'
		def new_dec(func):
			func.__order__ = order
			return func
		return new_dec


	@classmethod
	def tearDownClass(cls):
		pass


	@exe_order(0)
	def test_split_name(self):
		config = Config()

		for setting in self.settings:
			group = name = None
			if setting.valid_name:
				self.assertEquals(config.split_name(setting.fullname), (setting.group, setting.name))
			else:
				with self.assertRaises(SettingError) as e:
					config.split_name(setting.fullname)


	@exe_order(1)
	@insert_data
	def test_set(self):
		config = Config()

		for setting in self.settings:
			if setting.valid_name:
				if setting.valid_new_value:
					config.set(setting.fullname, setting.new_value)
				else:
					with self.assertRaises(SettingError) as e:
						config.set(setting.fullname, setting.new_value)


	@exe_order(2)
	def test_get(self):
		config = Config()

		for setting in self.settings:
			if setting.valid_name:
				value = config.get(setting.fullname)
				if setting.valid_new_value:
					new_value = setting.new_value
					if type(new_value) != setting.vtype:
						try:
							new_value = setting.vtype(new_value)
						except ValueError as e:
							print('new value not auto convertible to target type, correct test data')
					self.assertEquals(value, new_value)
				else:
					self.assertEquals(value, setting.value)


if __name__ == '__main__':
	ut_main()
