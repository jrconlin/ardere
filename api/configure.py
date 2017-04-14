import os
import json
import re

import toml
import yaml

from argparse import ArgumentParser


class Parser(object):
    """Template abstractor"""

    def __init__(self, load, dump):
        self.load = load
        self.dump = dump


def load_args():
    parser = ArgumentParser(description="Configure the input yml file")
    parser.add_argument('--template',
                        dest="template",
                        default="template.yml",
                        help="Source template file")
    parser.add_argument('--template_type',
                        dest="template_type",
                        help="Source template file type")
    parser.add_argument('--options',
                        dest="options",
                        default="options.yml",
                        help="File containing substitute values")
    parser.add_argument('--option_type',
                        dest="options_type",
                        help="Option file type")
    parser.add_argument('--output',
                        dest="output",
                        default="serverless.yml",
                        help="Output file")
    return parser.parse_args(), parser


def get_parser(filename, file_type):
    """Generate absctractor from type type hints provided."""
    if not file_type:
        file_type = os.path.splitext(filename)[1][1:]
    if file_type in ['toml', 'tml']:
        return Parser(toml.loads, toml.dump)
    if file_type in ['yaml', 'yml']:
        return Parser(yaml.load, yaml.dump)
    if file_type in ['json', 'js']:
        return Parser(json.loads, json.dumps)
    raise Exception("Unknown file {}".format(filename))


def loadfile(parser, filename):
    """Load based on file type"""
    if not filename:
        raise Exception("No file to load")
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


def convert(parser, data):
    """Convert native data to export type"""
    parser.dump(json.loads(data))


def main():
    try:
        args, parser = load_args()
        t_parse = get_parser(args.template, args.template_type)
        o_parse = get_parser(args.options, args.options_type)
        options = loadfile(o_parse, args.options)
        template = first_pass(args.template, options)
        with open(args.output, "w") as output:
            data = t_parse.load(template)
            output.write(yaml.dump(data))
    except Exception as ex:
        print("Failed to generate file\n{}\n".format(ex))
        parser.print_help()
        exit(-1)
    print("done")

if __name__ == "__main__":
    main()
