import os
import json
import re

import toml
import yaml

from argparse import ArgumentParser


class ConfigError(Exception):
    pass


class Parser(object):
    """Template abstractor"""

    def __init__(self, load, dump):
        self.load = load
        self.dump = dump


def load_args(args=None):
    parser = ArgumentParser(description="Configure the input yml file")
    parser.add_argument('--template',
                        dest="template",
                        default="template.yml",
                        help="Source template file")
    parser.add_argument('--template_type',
                        dest="template_type",
                        help="[optional] force source template file type")
    parser.add_argument('--options',
                        action="append",
                        dest="options",
                        default=[],
                        help="Files containing substitute values"
                        "Values in later files replace former, So"
                        "for `--options foo.yml --options bar.yml` "
                        "values in `bar.yml` replace `foo.yml`")
    parser.add_argument('--option_type',
                        dest="options_type",
                        help="[optional] force the Option file type")
    parser.add_argument('--output',
                        dest="output",
                        default="serverless.yml",
                        help="Output file")
    return parser.parse_args(args), parser


def get_parser(filename, file_type=None):
    """Generate absctractor from type type hints provided."""
    if not file_type:
        file_type = os.path.splitext(filename)[1][1:]
    if file_type in ['toml', 'tml']:
        return Parser(toml.loads, toml.dump)
    if file_type in ['yaml', 'yml']:
        return Parser(yaml.load, yaml.dump)
    if file_type in ['json', 'js']:
        return Parser(json.loads, json.dumps)
    raise ConfigError("Unknown file {}".format(filename))


def load_file(parser, filename):
    """Load based on file type"""
    if not filename:
        raise ConfigError("No file to load")
    with open(filename) as source:
        return parser.load(source)


def first_pass(filename, options):
    """Read the file line by line and do variable substitutions."""
    pattern = re.compile('{{([^ }]+)}}')

    result = []
    with open(filename) as source:
        for line in source:
            for item in pattern.findall(line):
                if options.get(item):
                    repl = options[item]
                    # Convert the value into yaml if needed
                    # strings are semi-special.
                    if not isinstance(options[item], str):
                        repl = yaml.dump(options[item])
                    line = line.replace(
                        "{{{{{}}}}}".format(item), repl)
            result.append(line)
    return ''.join(result)


def main():  # pragma: nocover
    try:
        args, parser = load_args()
        t_parse = get_parser(args.template, args.template_type)
        args.options = args.options or ['options.yml']
        o_parse = get_parser(args.options[0],
                             args.options_type)
        options = {}
        for option in args.options:
            options.update(load_file(o_parse, option))
        template = first_pass(args.template, options)
        with open(args.output, "w") as output:
            data = t_parse.load(template)
            output.write(yaml.dump(data))
    except ConfigError as ex:
        print("Failed to generate file\n{}\n".format(ex))
        parser.print_help()
        exit(-1)
    print("done")

if __name__ == "__main__":  # pragma: nocover
    main()
