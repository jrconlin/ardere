import unittest
from io import StringIO
import json

import mock
import yaml
from argparse import ArgumentParser
from nose.tools import eq_, ok_, assert_raises

from api.configure import (
        Parser,
        load_args,
        get_parser,
        load_file,
        first_pass,
        ConfigError
        )

class TestConfigre(unittest.TestCase):
    def test_load_args(self):
        args={}
        r_args, parser = load_args(args)

        eq_(r_args.template, 'template.yml')
        eq_(r_args.options, 'options.yml')
        eq_(r_args.output, 'serverless.yml')
        ok_(isinstance(parser, ArgumentParser))

    def test_get_parser(self):
        import toml

        pp = get_parser('foo.toml')
        ok_(isinstance(pp, Parser))
        eq_(pp.load, toml.loads)
        pp = get_parser('foo', 'yml')
        eq_(pp.load, yaml.load)
        pp = get_parser('foo.bar', 'json')
        eq_(pp.load, json.loads)
        assert_raises(ConfigError, get_parser, 'foo', 'bar')


    @mock.patch('api.configure.open')
    def test_load_file(self, mopen):
        mopen.return_value = StringIO(u'{"foo": "bar"}')
        parser = Parser(json.load, json.dumps)
        src = load_file(parser, 'foo')
        eq_(src.get('foo'), 'bar')
        assert_raises(ConfigError, load_file, None, None)

    @mock.patch('api.configure.open')
    def test_first_pass(self, mopen):
        mopen.return_value = StringIO(u'Test={{foo}}')
        result = first_pass("foo", {"foo": ["alpha", "beta"]})
        eq_(result, u'Test=[alpha, beta]\n')
