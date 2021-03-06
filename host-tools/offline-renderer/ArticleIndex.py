#! /usr/bin/env python
# -*- coding: utf-8 -*-
# COPYRIGHT: Openmoko Inc. 2010
# LICENSE: GPL Version 3 or later
# DESCRIPTION: Create Article Indices
# AUTHORS: Sean Moss-Pultz <sean@openmoko.com>
#          Christopher Hall <hsw@openmoko.com>

from __future__ import with_statement
import os, sys, re
import struct
import littleparser
import getopt
import os.path
import time
import subprocess
import sqlite3
import FilterWords
import FileScanner
import TidyUp
import PrintLog


# this _must_ be in ascending ASCII sequence
KEYPAD_KEYS = """ !#$%&'()*+,-.0123456789=?@abcdefghijklmnopqrstuvwxyz"""

# to check if in order: uncomment and look at result
#for c in KEYPAD_KEYS:
#    print('{0:d}'.format(ord(c)))
#sys.exit(0)


# underscore and space
whitespaces = re.compile(r'([\s_]+)', re.IGNORECASE)

# to catch loop in redirections
class CycleError(Exception):
    pass


verbose = False
enable_templates = True     # $$$ When this is false, templates are included as articles :/
error_flag = False          # indicates error in indexing, but processing will still continue
                            # to find more errors

bigram = {}


def usage(message):
    if None != message:
        print('error: {0:s}'.format(message))
    print('usage: {0:s} <options> xml-file...'.format(os.path.basename(__file__)))
    print('       --help                  This message')
    print('       --verbose               Enable verbose output')
    print('       --article-index=file    Article index database output [articles.db]')
    print('       --article-offsets=file  Article file offsets database output [offsets.db]')
    print('       --article-counts=file   File to store the counts [counts.text]')
    print('       --limit=number          Limit the number of articles processed')
    print('       --prefix=name           Device file name portion for .fnd/.pfx [pedia]')
    print('       --templates=file        Database for templates [templates.db]')
    exit(1)


def main():
    global verbose
    global error_flag

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hvi:o:c:t:l:p:',
                                   ['help', 'verbose',
                                    'article-index=',
                                    'article-offsets=',
                                    'article-counts=',
                                    'templates=',
                                    'limit=',
                                    'prefix='])
    except getopt.GetoptError, err:
        usage(err)

    verbose = False
    art_name = "articles.db"
    off_name = "offsets.db"
    cnt_name = "counts.text"
    fnd_name = 'pedia.fnd'
    pfx_name = 'pedia.pfx'
    template_name = 'templates.db'
    limit = 'all'

    for opt, arg in opts:
        if opt in ('-v', '--verbose'):
            verbose = True
        elif opt in ('-h', '--help'):
            usage(None)
        elif opt in ('-i', '--article-index'):
            art_name = arg
        elif opt in ('-o', '--article-offsets'):
            off_name = arg
        elif opt in ('-c', '--article-counts'):
            cnt_name = arg
        elif opt in ('-t', '--templates'):
            template_name = arg
        elif opt in ('-l', '--limit'):
            if arg[-1] == 'k':
                arg = arg[:-1] + '000'
            if arg != 'all':
                try:
                    limit = int(arg)
                except ValueError:
                    usage('"{0:s}={1:s}" is not numeric'.format(opt, arg))
            if limit <= 0:
                usage('"{0:s}={1:s}" must be > zero'.format(opt, arg))
        elif opt in ('-p', '--prefix'):
            fnd_name = arg + '.fnd'
            pfx_name = arg + '.pfx'
        else:
            usage('unhandled option: ' + opt)

    if [] == args:
        usage('Missing argument(s)')

    processor = FileProcessing(articles = art_name, offsets = off_name, templates = template_name)

    for f in args:
        limit = processor.process(f, limit)
        if limit != 'all' and limit <= 0:
            break

    # record initial counts
    a = processor.article_count
    r = processor.redirect_count

    # fix up redirects
    m = a + processor.resolve_redirects()

    # record combined count and display statistics
    s = a + r

    cf = open(cnt_name, 'w')

    for f in (sys.stdout, cf):
        f.write('Articles:   {0:10d}\n'.format(a))
        f.write('Redirects:  {0:10d}\n'.format(r))
        f.write('Sum:        {0:10d}\n'.format(s))
        f.write('Merged:     {0:10d}\n'.format(m))
        f.write('Difference: {0:10d}\n'.format(m - s))

        f.write('Restricted: {0:10d}\n'.format(processor.restricted_count))

        f.write('Templates:  {0:10d}\n'.format(processor.template_count))
        f.write('rTemplates: {0:10d}\n'.format(processor.template_redirect_count))

        f.write('Characters: {0:10d}\n'.format(processor.total_character_count))

    cf.close()

    output_fnd(fnd_name, processor)
    output_pfx(pfx_name)
    del processor

    # return non-zero status if there have been any errors
    if error_flag:
        PrintLog.message('*** ERROR in Index build')
        PrintLog.message('***   Currently "Duplicate Title" is the only condition that causes this error')
        PrintLog.message('***   Likely "license.xml" or "terms.xml" file duplicates a title in main wiki file')
        PrintLog.message('***   Manually edit "license.xml" or "terms.xml" file to change the title')
        sys.exit(1)


def generate_bigram(text):
    global bigram
    if len(text) > 2:
        try:
            if text[0].lower() in KEYPAD_KEYS and text[1].lower() in KEYPAD_KEYS:
                bigram[text[0:2]] += 1
        except KeyError:
            bigram[text[0:2]] = 1

    if len(text) > 4:
        try:
            if text[2].lower() in KEYPAD_KEYS and text[3].lower() in KEYPAD_KEYS:
                bigram[text[2:4]] += 1
        except KeyError:
            bigram[text[2:4]] = 1


class FileProcessing(FileScanner.FileScanner):

    def __init__(self, *args, **kw):
        super(FileProcessing, self).__init__(*args, **kw)

        self.article_db_name = kw['articles']
        self.article_import = self.article_db_name + '.import'

        self.offset_db_name = kw['offsets']
        self.offset_import = self.offset_db_name + '.import'
        self.file_import = self.offset_db_name + '.files'

        self.template_db_name = kw['templates']

        for filename in [self.article_db_name,
                         self.article_import,
                         self.offset_db_name,
                         self.offset_import,
                         self.template_db_name,
                         self.file_import]:
            if os.path.exists(filename):
                os.remove(filename)

        self.restricted_count = 0
        self.redirect_count = 0
        self.article_count = 0
        self.template_count = 0
        self.template_redirect_count = 0

        self.all_titles = []

        self.translate = littleparser.LittleParser().translate
        self.redirects = {}

        self.articles = {}
        self.offsets = {}

        self.total_character_count = 0

        self.time = time.time()

        self.template_db = sqlite3.connect(self.template_db_name)
        self.template_db.execute('pragma synchronous = 0')
        self.template_db.execute('pragma temp_store = 2')
        self.template_db.execute('pragma read_uncommitted = true')
        self.template_db.execute('pragma cache_size = 20000000')
        self.template_db.execute('pragma default_cache_size = 20000000')
        self.template_db.execute('pragma journal_mode = off')
        self.template_db.execute('''
create table templates (
    title varchar primary key,
    body varchar
)
''')
        self.template_db.execute('''
create table redirects (
    title varchar primary key,
    redirect varchar
)
''')
        self.template_db.commit()
        self.template_cursor = self.template_db.cursor()


    def __del__(self):
        PrintLog.message(u'Flushing databases')
        self.template_db.commit()
        self.template_cursor.close()
        self.template_db.close()

        PrintLog.message(u'Writing: files')
        start_time = time.time()
        i = 0
        with open(self.file_import, 'w') as f:
            for filename in self.file_list:
                f.write('{0:d}\t{1:s}\n'.format(i, filename))
                i += 1
        PrintLog.message(u'Time: {0:7.1f}s'.format(time.time() - start_time))

        PrintLog.message(u'Writing: articles')
        start_time = time.time()
        with open(self.article_import, 'w') as f:
            for title in self.articles:
                (article_number, fnd_offset, restricted) = self.articles[title]
                f.write('~' + title.encode('utf-8'))    # force string
                f.write('\t{0:d}\t{1:d}\t{2:d}\n'.format(article_number, fnd_offset, restricted))
        PrintLog.message(u'Time: {0:7.1f}s'.format(time.time() - start_time))

        PrintLog.message(u'Writing: offsets')
        start_time = time.time()
        with open(self.offset_import, 'w') as f:
            for article_number in self.offsets:
                (file_id, title, seek, length, accumulated) = self.offsets[article_number]
                f.write('{0:d}\t{1:d}\t'.format(article_number, file_id))
                f.write('~' + title.encode('utf-8'))    # force string
                f.write('\t{0:d}\t{1:d}\t{2:d}\n'.format(seek, length, accumulated))
        PrintLog.message(u'Time: {0:7.1f}s'.format(time.time() - start_time))


        PrintLog.message(u'Loading: articles')
        start_time = time.time()
        p = subprocess.Popen('sqlite3 > /dev/null 2>&1 ' + self.article_db_name, shell=True, stdin=subprocess.PIPE)
        p.stdin.write("""
create table articles (
    title varchar primary key,
    article_number integer,
    fnd_offset integer,
    restricted varchar
);

pragma synchronous = 0;
pragma temp_store = 2;
pragma locking_mode = exclusive;
pragma cache_size = 20000000;
pragma default_cache_size = 20000000;
pragma journal_mode = memory;

.mode tabs
.import {0:s} articles
.exit
""".format(self.article_import))
        p.stdin.close()
        p.wait()
        PrintLog.message(u'Time: {0:7.1f}s'.format(time.time() - start_time))

        PrintLog.message(u'Loading: offsets and files')
        start_time = time.time()
        p = subprocess.Popen('sqlite3 > /dev/null 2>&1 ' + self.offset_db_name, shell=True, stdin=subprocess.PIPE)
        p.stdin.write("""
create table offsets (
    article_number integer primary key,
    file_id integer,
    title varchar,
    seek integer,
    length integer,
    accumulated integer
);

create table files (
    file_id integer primary key,
    filename varchar
);

pragma synchronous = 0;
pragma temp_store = 2;
pragma locking_mode = exclusive;
pragma cache_size = 20000000;
pragma default_cache_size = 20000000;
pragma journal_mode = memory;

.mode tabs
.import {0:s} offsets
.import {1:s} files
.exit
""".format(self.offset_import, self.file_import))
        p.stdin.close()
        p.wait()
        PrintLog.message(u'Time: {0:7.1f}s'.format(time.time() - start_time))


    def title(self, category, key, title, seek):
        global verbose
        global enable_templates

        if self.KEY_ARTICLE == key:
            return True

        if enable_templates and self.KEY_TEMPLATE == key:
            if verbose:
                PrintLog.message(u'Template Title: {0:s}'.format(unicode(title, 'utf-8')))
            return True

        return False


    def redirect(self, category, key, title, rcategory, rkey, rtitle, seek):
        global whitespaces
        global verbose

        title = self.translate(title).strip(u'\u200e\u200f')

        rtitle = self.translate(rtitle).strip().strip(u'\u200e\u200f')
        rtitle = whitespaces.sub(' ', rtitle).strip().lstrip(':')

        if self.KEY_TEMPLATE == key:
            if title != rtitle:
                title = unicode(category, 'utf-8') + ':' + title.lower()
                rtitle = unicode(rcategory, 'utf-8') + ':' + rtitle.lower()
                self.template_cursor.execute(u'insert or replace into redirects (title, redirect) values(?, ?)',
                                             [u'~{0:d}~{1:s}'.format(self.file_id(), title),
                                              u'~{0:d}~{1:s}'.format(self.file_id(), rtitle)])

            self.template_redirect_count += 1
            return

        if self.KEY_ARTICLE != key or self.KEY_ARTICLE != rkey:
            if verbose:
                PrintLog.message(u'Non-article Redirect: {0:s}[{1:d}]:{2:s} ->  {3:s}[{4:d}]:{5:s}'
                                 .format(category, key, title, rcategory, rkey, rtitle))
            return

        if '' == rtitle:
            PrintLog.message(u'Empty Redirect for: {0:s}[{1:d}]:{2:s}'.format(category, key, title))
        else:
            self.redirects[title] = rtitle
            self.redirect_count += 1
            if verbose:
                PrintLog.message(u'Redirect: {0:s}[{1:d}]:{2:s} ->  {3:s}[{4:d}]:{5:s}'
                                 .format(category, key, title, rcategory, rkey, rtitle))


    def body(self, category, key, title, text, seek):
        global verbose
        global error_flag

        title = self.translate(title).strip(u'\u200e\u200f')

        if self.KEY_TEMPLATE == key:
            t1 = unicode(category, 'utf-8') + ':' + title.lower()
            t_body = TidyUp.template(text)
            self.template_cursor.execute(u'insert or replace into templates (title, body) values(?, ?)',
                                         [u'~{0:d}~{1:s}'.format(self.file_id(), t1), u'~' + t_body])
            self.template_count += 1
            return

        restricted = FilterWords.is_restricted(title) or FilterWords.is_restricted(text)

        self.article_count += 1

        # do closer inspection to see if realy restricted
        if restricted:
            (restricted, bad_words) = FilterWords.find_restricted(text)

        if restricted:
            self.restricted_count += 1

        if not verbose and self.article_count % 10000 == 0:
            start_time = time.time()
            PrintLog.message(u'Index: {0:7.2f}s {1:10d}'.format(start_time - self.time, self.article_count))
            self.time = start_time

        generate_bigram(title)

        if verbose:
            if restricted:
                PrintLog.message(u'Restricted Title: {0:s}'.format(title))
                PrintLog.message(u'  --> {0:s}'.format(bad_words))
            else:
                PrintLog.message(u'Title: {0:s}'.format(title))

        character_count = len(text)
        self.total_character_count += character_count
        self.offsets[self.article_count] = (self.file_id(), title, seek, character_count, self.total_character_count)

        if self.set_index(title, (self.article_count, -1, restricted)): # -1 == pfx place holder
            PrintLog.message(u'ERROR: Duplicate Title: {0:s}'.format(title))
            error_flag = True


    def resolve_redirects(self):
        """add redirect to article_index"""
        count = 0
        for item in self.redirects:
            try:
                self.set_index(item, self.find(item))
                count += 1
            except KeyError:
                PrintLog.message(u'Unresolved redirect: {0:s} -> {1:s}'.format(item, self.redirects[item]))
            except CycleError:
                PrintLog.message(u'Cyclic redirect: {0:s} -> {1:s}'.format(item, self.redirects[item]))
        return count


    def set_index(self, title, data):
        """returns false if the key did not already exist"""
        if type(title) == str:
            title = unicode(title, 'utf-8')
        result = title in self.articles
        self.articles[title] = data
        return result


    def get_index(self, title):
        if type(title) == str:
            title = unicode(title, 'utf-8')
        return self.articles[title]


    def all_indices(self):
        return self.articles.keys()


    def find(self, title, level = 0):
        """get index from article title

        also handles redirects
        returns: [index, fnd]
        """
        if '' == title:
            raise CycleError('Empty title detected')
        if level > 10:
            raise CycleError('Redirect cycle: ' + title)
        try:
            title = self.redirects[title]
        except KeyError:
            title = self.redirects[title[0].swapcase() + title[1:]]

        try:
            result = self.get_index(title)
        except KeyError:
            try:
                result = self.get_index(title[0].swapcase() + title[1:])
            except:
                result = self.find(title, level + 1)
        return result


import unicodedata
def strip_accents(s):
    if type(s) == str:
        s = unicode(s, 'utf-8')
    return ''.join((c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn'))


def bigram_encode(title):
    global bigram

    result = ''
    title = strip_accents(title)

    while len(title) >= 2:
        if title[0].lower() in KEYPAD_KEYS:

            b = title[0:2]
            if b in bigram:
                result += bigram[b]
                title = title[2:]
            else:
                result += chr(ord(title[0:1]))
                title = title[1:]
        else:
            #result += '?'
            title = title[1:]
    if len(title) == 1:
        if title[0].lower() in KEYPAD_KEYS:
            result += chr(ord(title[0]))
        #else:
        #    result += '?'
    return result


def output_fnd(filename, article_index):
    """create bigram table"""
    global bigram
    global index_matrix

    PrintLog.message(u'Writing bigrams: {0:s}'.format(filename))
    start_time = time.time()
    out_f = open(filename, 'w')

    sortedgram = [ (value, key) for key, value in bigram.iteritems() ]
    sortedgram.sort()
    sortedgram.reverse()

    bigram = {}
    i = 0
    for k, v in sortedgram:
        out_f.write(v)
        bigram[v] = chr(i + 128)
        i += 1
        if i >= 128:
            break
    while i < 128:
        out_f.write('zz')
        bigram['zz'] = chr(i + 128)
        i += 1

    PrintLog.message(u'Time: {0:7.1f}s'.format(time.time() - start_time))

    # create pfx matrix and write encoded titles

    #article_list = [strip_accents(k) for k in article_index.keys()]
    #article_list.sort(key = lambda x: strip_accents(x).lower())

    def sort_key(key):
        global KEYPAD_KEYS
        return ''.join(c for c in strip_accents(key).lower() if c in KEYPAD_KEYS)

    PrintLog.message(u'Sorting titles')
    start_time = time.time()

    article_list = [ (sort_key(title), title) for title in article_index.all_indices() ]
    article_list.sort()

    PrintLog.message(u'Time: {0:7.1f}s'.format(time.time() - start_time))

    PrintLog.message(u'Writing matrix: {0:s}'.format(filename))
    start_time = time.time()

    index_matrix = {}
    index_matrix['\0\0\0'] = out_f.tell()
    for stripped_title, title in article_list:
        offset = out_f.tell()
        key3 = (title[0:3] + '\0\0\0')[0:3].lower()
        key2 = key3[0:2] + '\0'
        key1 = key3[0:1] + '\0\0'
        if key1 not in index_matrix:
            index_matrix[key1] = offset
        if key2 not in index_matrix:
            index_matrix[key2] = offset
        if key3 not in index_matrix:
            index_matrix[key3] = offset
        (article_number, dummy, restricted) = article_index.get_index(title)
        article_index.set_index(title, (article_number, offset, restricted))
        out_f.write(struct.pack('Ib', article_number, 0) + bigram_encode(title) + '\0')

    out_f.close()
    PrintLog.message(u'Time: {0:7.1f}s'.format(time.time() - start_time))


def output_pfx(filename):
    """output the pfx matrix"""
    global index_matrix

    PrintLog.message(u'Writing: {0:s}'.format(filename))
    start_time = time.time()
    out_f = open(filename, 'w')
    list = '\0' + KEYPAD_KEYS
    for k1 in list:
        for k2 in list:
            for k3 in list:
                key = k1+k2+k3
                if key in index_matrix:
                    offset = index_matrix[key]
                else:
                    offset = 0
                out_f.write(struct.pack('I', offset))

    out_f.close()
    PrintLog.message(u'Time: {0:7.1f}s'.format(time.time() - start_time))


# run the program
if __name__ == "__main__":
    main()
