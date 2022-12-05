#!/usr/bin/env python3
'''
  Purpose:
           run sql to get a test set of refs for GXD secondary triage analysis.
           Include all extracted text sections except references and supp data.
           (minor) Data transformations include:
            lower case all text
            replacing non-ascii chars with ' '
            replacing FIELDSEP and RECORDSEP chars in the doc text w/ ' '
            Keep paragraph boundaries ('\n\n') to enable finding of figure
                legends.

  Outputs:      Delimited file to specified output file.
                See GXDrefSample.ClassifiedSample for output format
'''
import sys
import os
import time
import argparse
import subprocess
import unittest
import db
import Pdfpath
import extractedTextSplitter
import GXDrefSample as SampleLib
from utilsLib import removeNonAscii

#-----------------------------------

sampleObjType = SampleLib.ClassifiedRefSample

# for the Sample output file
RECORDEND    = sampleObjType.getRecordEnd()
FIELDSEP     = sampleObjType.getFieldSep()

MINTEXTLENGTH = 200      # skip refs with extracted text shorter than this
#-----------------------------------

def getArgs():

    parser = argparse.ArgumentParser( \
        description='Get test set for GXD 2ndary triage proto.')

    parser.add_argument('option', action='store', default='counts',
        choices=['routed', 'notRoutedKeep', 'notRoutedDiscard', 'ids','test'],
        help='get samples, IDs from stdin, or just run automated tests')

    parser.add_argument('outFile', action='store', default='-',
        help='output file to write to. "-" for stdout.')

    parser.add_argument('--frompdf', dest='fromPDF', action='store_true',
        required=False,
        help="extract text from the archived PDFs instead of from db")

    parser.add_argument('-l', '--limit', dest='nResults',
        required=False, type=int, default=0, 		# 0 means ALL
        help="limit results to n references. Default is no limit")

    parser.add_argument('--textlength', dest='maxTextLength',
        type=int, required=False, default=None,
        help="only include the 1st n chars of text fields (for debugging)")

    parser.add_argument('-q', '--quiet', dest='verbose', action='store_false',
        required=False, help="skip helpful messages to stderr")

    defaultHost = os.environ.get('PG_DBSERVER', 'bhmgidevdb01')
    defaultDatabase = os.environ.get('PG_DBNAME', 'prod')

    parser.add_argument('-s', '--server', dest='server', action='store',
        required=False, default=defaultHost,
        help='db server. Shortcuts:  adhoc, prod, dev, test. (Default %s)' %
                defaultHost)

    parser.add_argument('-d', '--database', dest='database', action='store',
        required=False, default=defaultDatabase,
        help='which database. Example: mgd (Default %s)' % defaultDatabase)

    args =  parser.parse_args()

    if args.server == 'adhoc':
        args.host = 'mgi-adhoc.jax.org'
        args.db = 'mgd'
    elif args.server == 'prod':
        args.host = 'bhmgidb01.jax.org'
        args.db = 'prod'
    elif args.server == 'dev':
        args.host = 'mgi-testdb4.jax.org'
        args.db = 'jak'
    elif args.server == 'test':
        args.host = 'bhmgidevdb01.jax.org'
        args.db = 'prod'
    else:
        args.host = args.server
        args.db = args.database

    return args
#-----------------------------------

args = getArgs()

#-----------------------------------

SQL_routed = """
-- select TP's: originally routed, and selected by curators
select b._refs_key, a.accid "ID", rt.term "relevance", r.confidence,
    st.term "GXD status", 'TP' "orig TP/FP", b.journal
from bib_refs b join bib_workflow_status s
    on (b._refs_key = s._refs_key and s.iscurrent =1
        and s._group_key = 31576665) -- current GXD status
join bib_workflow_status s2 on (b._refs_key = s2._refs_key
    and s2._group_key = 31576665 and s2._createdby_key = 1618) -- 2nd triage
join bib_workflow_relevance r on (b._refs_key = r._refs_key
    and r._createdby_key = 1617) -- relevance_classifier
join acc_accession a on (b._refs_key = a._object_key
    and a._mgitype_key = 1 and a._logicaldb_key = 1
    and a.prefixpart = 'MGI:')
join voc_term st on (s._status_key = st._term_key)
join voc_term s2t on (s2._status_key = s2t._term_key)
join voc_term rt on (r._relevance_key = rt._term_key)
where
b.isreviewarticle = 0
and s2._status_key = 31576670 -- routed
and s._status_key in (31576671, 31576673, 31576674) --chosen,indexed,full-coded
union
-- select FP's: originally routed, but rejected by curators
select b._refs_key, a.accid "ID", rt.term "relevance", r.confidence,
    st.term "GXD status", 'FP' "orig TP/FP", b.journal
from bib_refs b join bib_workflow_status s
    on (b._refs_key = s._refs_key and s.iscurrent =1
        and s._group_key = 31576665) -- current GXD status
join bib_workflow_status s2 on (b._refs_key = s2._refs_key
    and s2._group_key = 31576665 and s2._createdby_key = 1618) -- 2nd triage
join bib_workflow_relevance r on (b._refs_key = r._refs_key
    and r._createdby_key = 1617) -- relevance_classifier
join acc_accession a on (b._refs_key = a._object_key
    and a._mgitype_key = 1 and a._logicaldb_key = 1
    and a.prefixpart = 'MGI:')
join voc_term st on (s._status_key = st._term_key)
join voc_term s2t on (s2._status_key = s2t._term_key)
join voc_term rt on (r._relevance_key = rt._term_key)
where
b.isreviewarticle = 0
and s2._status_key = 31576670 -- routed
and s._status_key in (31576672) -- Rejected
"""

SQL_notRoutedKeep = """
-- select refs originally not routed (no "embryo").
-- Just keepers and after June 1 2021 for not
select b._refs_key, a.accid "ID", rt.term "relevance", r.confidence,
        st.term "GXD status", 'NE' "orig TP/FP", b.journal
from bib_refs b join bib_workflow_status s
    on (b._refs_key = s._refs_key and s.iscurrent =1
        and s._group_key = 31576665) -- current GXD status
join bib_workflow_status s2 on (b._refs_key = s2._refs_key
    and s2._group_key = 31576665 and s2._createdby_key = 1618) -- 2nd triage
join bib_workflow_relevance r on (b._refs_key = r._refs_key
    and r._createdby_key = 1617) -- relevance_classifier
join acc_accession a on (b._refs_key = a._object_key
    and a._mgitype_key = 1 and a._logicaldb_key = 1
    and a.prefixpart = 'MGI:')
join voc_term st on (s._status_key = st._term_key)
join voc_term s2t on (s2._status_key = s2t._term_key)
join voc_term rt on (r._relevance_key = rt._term_key)
where
b.isreviewarticle = 0
and s2._status_key = 31576669 -- not routed
and rt.term = 'keep'
and b.creation_date > '6/1/2021'
"""

SQL_notRoutedDiscard = """
-- select refs originally not routed (no "embryo").
-- Just discards and after June 1 2021 for not
select b._refs_key, a.accid "ID", rt.term "relevance", r.confidence,
        st.term "GXD status", 'NE' "orig TP/FP", b.journal
from bib_refs b join bib_workflow_status s
    on (b._refs_key = s._refs_key and s.iscurrent =1
        and s._group_key = 31576665) -- current GXD status
join bib_workflow_status s2 on (b._refs_key = s2._refs_key
    and s2._group_key = 31576665 and s2._createdby_key = 1618) -- 2nd triage
join bib_workflow_relevance r on (b._refs_key = r._refs_key
    and r._createdby_key = 1617) -- relevance_classifier
join acc_accession a on (b._refs_key = a._object_key
    and a._mgitype_key = 1 and a._logicaldb_key = 1
    and a.prefixpart = 'MGI:')
join voc_term st on (s._status_key = st._term_key)
join voc_term s2t on (s2._status_key = s2t._term_key)
join voc_term rt on (r._relevance_key = rt._term_key)
where
b.isreviewarticle = 0
and s2._status_key = 31576669 -- not routed
and rt.term = 'discard'
and b.creation_date > '6/1/2021'
"""

# SQL for id list. Force MGI ID in the results as this is needed to extract
#  text from PDFs and the IDs in the input may be a J# or PMID or something.
SQL_IDs = """
-- select refs by list of IDs
select b._refs_key, a.accid "ID", mgi.accid "mgiID", rt.term "relevance",
    r.confidence, st.term "GXD status", 'TP' "orig TP/FP", b.journal
from bib_refs b join bib_workflow_status s
    on (b._refs_key = s._refs_key and s.iscurrent =1
        and s._group_key = 31576665) -- current GXD status
left join bib_workflow_relevance r on (b._refs_key = r._refs_key
    and r._createdby_key = 1617) -- relevance_classifier
join acc_accession a on (b._refs_key = a._object_key
    and a._mgitype_key = 1 and a._logicaldb_key = 1)
join acc_accession mgi on (b._refs_key = mgi._object_key
    and mgi._mgitype_key = 1 and mgi._logicaldb_key = 1
    and mgi.prefixpart = 'MGI:')
join voc_term st on (s._status_key = st._term_key)
left join voc_term rt on (r._relevance_key = rt._term_key)
where
a.accid in (%s)
"""
#-----------------------------------

def doSamples(sql):
    ''' Write known samples to args.outFile.
        Write error msgs to stdout.
        Write progress msgs to stderr.
        sql can be a string (single sql command set) OR a list of strings
    '''
    startTime = time.time()
    verbose("%s\nHitting database %s %s as mgd_public\n" % \
                                        (time.ctime(), args.host, args.db,))

    outputSampleSet = SampleLib.ClassifiedSampleSet(sampleObjType=sampleObjType)
    outputSampleSet.setMetaItem('host', args.host)
    outputSampleSet.setMetaItem('db', args.db)

    # Build sql
    if type(sql) == type(''):   # force a list
        sqlList = [sql]
    else:
        sqlList = sql

    if args.nResults != 0:      # limit number of results for debugging?
        limitClause = 'limit %d\n' % args.nResults
        sqlList = [sqlList[0] + limitClause]    # just 1st query + limitClause

    # Run it
    for sql in sqlList:
        results = db.sql(sql, 'auto')

        # Create sample records and add to SampleSet
        for i,r in enumerate(results):
            if i % 200 == 0: verbose("..%d\n" % i)
            if not args.fromPDF:        # get from db
                text = getText4Ref_fromDB(r['_refs_key'])
            else:                       # extract text from PDF
                mgiID = r['ID']      # we need an MGI ID to find the PDF
                if not mgiID.startswith('MGI:'):
                    if r.has_key('mgiID'):
                        mgiID = r['mgiID']
                    else:
                        msg = 'Error on record %d:\n%s\n' % (i, str(r))
                        msg += 'need MGI ID to get text from PDF\n'
                        raise RuntimeError(msg)

                text, error = getText4Ref_fromPDF(mgiID)
                if error:
                    sys.stdout.write("Skipping %s:\n%s" % (r['ID'], error))
                    continue

            if len(text) < MINTEXTLENGTH:
                sys.stdout.write("Skipping %s, text length is %d\n" % \
                                                    (r['ID'], len(text)) )
                continue

            text = cleanUpTextField(text) + '\n'
            try:
                sample = sqlRecord2ClassifiedSample(r, text)
                outputSampleSet.addSample(sample)
            except:         # if some error, try to report which record
                sys.stderr.write("Error on record %d:\n%s\n" % (i, str(r)))
                raise
        # Write output - for all the rcds in the dataset so far
        # This overwrites the file each time, but it is better than saving everything
        #  until the end and getting no output if some error kills the whole process.
        outputSampleSet.setMetaItem('time', time.strftime("%Y/%m/%d-%H:%M:%S"))
        outputSampleSet.write(args.outFile)
    # end for sql in sqlList

    verbose('\n')
    verbose("wrote %d samples to '%s'\n" % (outputSampleSet.getNumSamples(),
                                            args.outFile))
    verbose("%8.3f seconds\n\n" %  (time.time()-startTime))

    return
#-----------------------------------

def sqlRecord2ClassifiedSample(r,               # sql Result record
    text,
    ):
    """
    Return a ClassifiedSample object for the sql record
    Encapsulates knowledge of ClassifiedSample.setFields() field names
    """
    newR = {}
    newSample = sampleObjType()

    if r['GXD status'] == 'Rejected':
        knownClassName = 'No'
    elif r['GXD status'] in ['Chosen', 'Indexed', 'Full-coded']:
        knownClassName = 'Yes'
    elif r['GXD status'] == 'Not Routed':
        knownClassName = 'No'   # if not routed, don't really know its class
                                # ..but we need to pick one
    else:
        raise ValueError("Invalid GXD status '%s'\n" % r['GXD status'])

    ## populate the Sample fields
    newR['knownClassName'] = knownClassName
    newR['ID']             = str(r['ID'])
    newR['_refs_key']      = str(r['_refs_key'])
    newR['relevance']      = str(r['relevance'])
    newR['confidence']     = str(r['confidence'])
    newR['orig TP/FP']     = str(r['orig TP/FP'])
    newR['GXD status']     = str(r['GXD status'])
    newR['journal']        = str(r['journal'])
    newR['text']           = text

    return newSample.setFields(newR)
#-----------------------------------

splitter = extractedTextSplitter.ExtTextSplitter()

def getText4Ref_fromPDF(mgiID):
    """ Return (text, error)
        text = extracted text (string) - in lower case - from the PDF.
            for the specified MGI ID, omitting the refs and supp data sections
        error = None or an error message if the text could not be extracted.
    """
    PDF_STORAGE_BASE_PATH = '/data/littriage'
    prefix, numeric = mgiID.split(':')
    filePath = os.path.join(Pdfpath.getPdfpath(PDF_STORAGE_BASE_PATH,mgiID),
                                                            numeric + '.pdf')

    text, error = extractTextFromPdf(filePath)

    ## Split the text and get all but the reference and supp data sections
    (body, refs, manuFigures, starMethods, suppData) = \
                                                    splitter.splitSections(text)

    text = body + manuFigures + starMethods
    return text.lower(), error
#-----------------------------------

def extractTextFromPdf(pdfPathName):
    """ Return (text, error)
        text = the extracted text from the PDF,
        error = None or an error message if the text could not be extracted.
    """
    ## Get full text from PDF
    LITPARSER             = '/usr/local/mgi/live/mgiutils/litparser'
    executable = os.path.join(LITPARSER, 'pdfGetFullText.sh')

    cmd = [executable, pdfPathName]
    cmdText = ' '.join(cmd)
    
    completedProcess = subprocess.run(cmd, capture_output=True, text=True)

    if completedProcess.returncode != 0:
        text = ''
        error = "pdftotext error: %d\n%s\n%s\n%s\n" % \
                        (completedProcess.returncode, cmdText,
                            completedProcess.stderr, completedProcess.stdout)
    else:
        text = completedProcess.stdout
        error = None

    return text, error
#-----------------------------------

def getText4Ref_fromDB(refKey):
    """ Return extracted text (string) - in lower case -
        from the DB.
        for the specified _refs_key
    """
    # sql to get extracted text, omitting reference and supplemental sections
    extractedSql = '''
        select distinct lower(d.extractedText) as extractedText
        from bib_workflow_data d
        where d._refs_key = %s
        and d._extractedtext_key not in (48804491, 48804492)
        and d.extractedText is not null
    '''
    results = db.sql(extractedSql % (refKey), 'auto')
    textparts = [ r['extractedtext'] for r in results]

    return ''.join(textparts)
#-----------------------------------

def cleanUpTextField(text):

    if text == None:
        text = ''

    if args.maxTextLength:	# handy for debugging
        text = text[:args.maxTextLength]

    text = removeNonAscii(cleanDelimiters(text))
    text = text.replace('\r', ' ')
    return text
#-----------------------------------

def cleanDelimiters(text):
    """ remove RECORDEND and FIELDSEPs from text (replace w/ ' ')
    """
    return text.replace(RECORDEND,' ').replace(FIELDSEP,' ')
#-----------------------------------

def verbose(text):
    if args.verbose:
        sys.stderr.write(text)
        sys.stderr.flush()
#-----------------------------------

def doAutomatedTests():

    #sys.stdout.write("No automated tests at this time\n")
    #return

    sys.stdout.write("%s\nHitting database %s %s as mgd_public\n" % \
                                        (time.ctime(), args.host, args.db,))
    sys.stdout.write("Running automated unit tests...\n")
    unittest.main(argv=[sys.argv[0], '-v'],)

class MyTests(unittest.TestCase):
    def test_getText4Ref(self):
        t = getText4Ref('11943') # no text
        self.assertEqual(t, '')

        t = getText4Ref('361931') # multiple sections
        expText = 'lnk/ mice.\n\n\n\nfig. 5.' # boundry body-author fig legends
        found = t.find(expText)
        self.assertNotEqual(found, -1)

#-----------------------------------

def main():
    db.set_sqlServer  (args.host)
    db.set_sqlDatabase(args.db)
    db.set_sqlUser    ("mgd_public")
    db.set_sqlPassword("mgdpub")

    if   args.option == 'test':    doAutomatedTests()
    elif args.option == 'routed':           doSamples(SQL_routed)
    elif args.option == 'notRoutedKeep':    doSamples(SQL_notRoutedKeep)
    elif args.option == 'notRoutedDiscard': doSamples(SQL_notRoutedDiscard)
    elif args.option == 'ids':
        ids = ["'%s'" % x.strip() for x in sys.stdin]
        verbose('Read %d IDs\n' % len(ids))
        step = 500      # num of IDs to format per sql stmt
        sqlList = []
        for start in range(0, len(ids), step):
            idSubset = ids[start:start+step]
            formattedIDs = ','.join(idSubset)
            sql = SQL_IDs % formattedIDs
            #print(sql)
            sqlList.append(sql)
        doSamples(sqlList)
    else: sys.stderr.write("invalid option: '%s'\n" % args.option)

    exit(0)
#-----------------------------------
if __name__ == "__main__":
    main()
