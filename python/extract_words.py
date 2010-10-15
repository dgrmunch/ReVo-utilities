#!/usr/bin/python

import os
import lxml.etree
import re
import json

from esperanto_sort import compare_esperanto_strings

def clean_string(string):
    """Discard newlines, remove multiple spaces and remove leading or
    trailing whitespace.

    >>> clean_string(' \nfoo   bar  \n  ')
    'foo bar'

    """

    return re.sub('[\n\t ]+', ' ', string).strip()

def get_words_from_kap(node):
    """Return a list of all the terms in a kap node. This is not
    necessarily single words, since ReVo includes entries such as
    'brazila nukso'.

    The heavy lifting is done in flatten_kap, all we do here is
    separate out terms and remove extraneous whitespace.

    Possible formats encountered:
    'foo'
    'foo, bar'
    'foo,\n   bar'
    '(n,p)-matrico' (only term in ReVo with an internal comma)

    """
    flat_string = flatten_kap(node)

    if flat_string == '(n,p)-matrico':
        words = ['(n,p)-matrico']
    else:
        words = flat_string.split(',')
    if len(words) > 1:
        for i in range(len(words)):
            # remove trailing/leading space and awkard newlines
            words[i] = clean_string(words[i])

    return words

def flatten_kap(kap):
    """Take everything between <kap> and </kap> and return a naked
    string. This will either be one word or multiple (usually
    separated by commas but I haven't checked whether this is
    universally true).

    For the interested reader, some examples:

    <kap><ofc>*</ofc><tld/>o</kap>
    <kap>brazil<tld/>arbo, <var><kap>brazila <tld/>arbo</kap></var></kap>
    (from nuks.xml)

    <kap><tld lit="A"/>o</kap>
    (from agl.xml)

    <kap><tld/>ino<fnt>Z</fnt></kap>
    (from hom.xml)

    <kap>
      <tld lit="S"/>lando
      <fnt>
        <vrk>Oficiala Informo de AdE</vrk>,
        <lok>numero 12</lok>
      </fnt>
    </kap>
    (from skot.xml)

    """
    assert kap != None
    root = get_word_root(kap)
    
    flat_string = ""
    if kap.text != None:
        flat_string += kap.text

    # flatten, get all the text, throw away ofc and fnt tags
    # this is not simple, but the xml structure is a pain
    for child in kap.getchildren():
        if child.tag == 'tld':
            """The lit attribute of a tld tag signifies that in this
            particular case the root starts with a different letter
            than normal. For example, 'Aglo' has root 'agl-'. I
            haven't seen this used for anything other than
            capitalisation (both changing to upper case and changing
            to lower case).

            The relevant part of the ReVo documentation is vokoxml.dtd,
            lines 340 to 344.

            """
            if "lit" in child.attrib.keys():
                new_letter = child.attrib['lit']
                flat_string += new_letter + root[1:]
            else:
                flat_string += root

            if child.text != None:
                flat_string += child.text
        elif child.tag == 'fnt':
            # we throw away source of word, not interested right now
            pass
        elif child.tag == 'ofc':
            # also throw away oficialness, not interested
            pass
        elif child.tag == 'var':
            # recurse -- egads! Why isn't the xml simpler?
            child_kap = child.getchildren()[0]
            flat_string += flatten_kap(child_kap)
        else:
            # shouldn't get here
            assert False
        if child.tail != None:
            flat_string += child.tail

    return clean_string(flat_string)

def get_word_root(arbitrary_node):
    """Get the word root corresponding to this word. The XML files are
    grouped such that every word in the same file has the same word
    root. We therefore do not need any specific node for this
    function.

    A minimal example:

    <vortaro>
    <kap><rad>salut</rad></kap>
    </vortaro>

    """
    assert arbitrary_node != None
    tree = arbitrary_node.getroottree()
    return list(tree.iter('rad'))[0].text

def get_tree(xml_file):
    parser = lxml.etree.XMLParser(load_dtd=True)
    return lxml.etree.parse(xml_file, parser)

def get_all_definitions(drv_node):
    # get all definitions for a word
    # this probably has bugs given the complexity of the input
    # some representative examples are:
    # sxilin.xml for subsenses
    # jakobi1.xml only <ref>, no <dif> node
    # frakci.xml only <ref> but huge and complex
    # ad.xml has a load of stuff, some of which is not documented

    definitions = []

    for sense in drv_node.findall('snc'):
        # every snc node is made up of <dif>s (definitions) or
        # <subsnc>s (subsenses)
        for node in sense.findall('dif'):
            definitions.append(get_definition(node))
        for subsense in sense.findall('subsnc'):
            for node in subsense.findall('dif'):
                definitions.append(get_definition(node))

    return definitions

def get_definition(dif_node):
    # convert a definition node to a simple unicode string
    # (this requires us to flatten it)

    definition = ""

    if dif_node.text:
        definition += dif_node.text
    for node in dif_node:
        if node.tag == 'ekz':
            # skip examples
            continue
        if node.text:
            definition += node.text
        if node.tail:
            definition += node.tail

    return clean_string(definition)


def get_entries(xml_file):
    """Get every entry from a given XML file: the words, their roots
    and their definitions.

    """

    tree = get_tree(xml_file)

    # each word is a drv node
    results = []
    for drv_node in tree.iter('drv'):
        node_words = get_words_from_kap(drv_node.find('kap'))
        root = get_word_root(drv_node)
        definitions = get_all_definitions(drv_node)
        for word in node_words:
            results.append((word, root, definitions))

    return results

def get_all_entries():
    """Extract all dictionary data from every XML file in the ../xml
    directory.

    """

    entries = []
    """For each root we assign a primary word, which is
    the first word we encounter with this root. This is
    the word we will link to the the morphology parser
    encounters the root.

    """
    roots_seen = []

    # fetch from xml files
    path = '../xml/'
    for file in [(path + file) for file in os.listdir(path)]:
        print file
        for (word, root, definitions) in get_entries(file):
            if root in roots_seen:
                entries.append({"word":word, "root":root,
                                "definitions":definitions, "primary":True})
            else:
                entries.append({"word":word, "root":root,
                                "definitions":definitions, "primary":False})

    # sort them
    get_word = (lambda x: x['word'])
    entries.sort(cmp=compare_esperanto_strings, key=get_word)

    # discard duplicates
    no_duplicates = [entries[0]]
    for i in range(1, len(entries)):
        if entries[i-1]['word'] != entries[i]['word']:
            no_duplicates.append(entries[i])

    return no_duplicates

if __name__ == '__main__':
    word_list = get_all_entries()

    output_file = open('dictionary.json', 'w')
    json.dump(word_list, output_file)
