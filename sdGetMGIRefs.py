#!/usr/bin/env python3
'''
  Purpose:
           run sql to get MGI references dataset
           (minor) Data transformations include:
            replacing non-ascii chars with ' '
            replacing FIELDSEP and RECORDSEP chars in the doc text w/ ' '

  Outputs:      Delimited file to stdout
                MLtextTools Sample File of MGIReference objects.
'''
#-----------------------------------
import sys
import os
import string
import re
import time
import argparse
import db
import MGIReference
from utilsLib import removeNonAscii
import ExtractedTextSet
#-----------------------------------

sampleObjType = MGIReference.MGIReference

# for the Sample output file
RECORDEND    = sampleObjType.getRecordEnd()
FIELDSEP     = sampleObjType.getFieldSep()
#-----------------------------------

def getArgs():

    parser = argparse.ArgumentParser( \
        description='Get MGI References set, write to stdout')

    parser.add_argument('--test', dest='test', action='store_true',
        required=False,
        help="just run automated test code")

    parser.add_argument('option', action='store', default='counts',
        choices=['selected', 'rejected', 'older', 'counts'],
        help='which subset of training samples to get or "counts" (default)')

    parser.add_argument('-o', '--output', dest='output',
        choices=['samplefile', 'table'], default='samplefile',
        help="Output format. Default is samplefile")

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
        args.host = args.server + '.jax.org'
        args.db = args.database

    return args
#-----------------------------------

args = getArgs()

####################
# SQL fragments used to build up queries
#    We build the queries in the following steps:
#    1) A tmp OMIT_TABLE of references to omit from the training set because
#        their ground truth may be questionable
#    2) a tmp BASE_TABLE of all refs NOT in the OMIT_TABLE and build an
#        index on creation_date for that table. This speeds things dramatically
#    3) a final tmp table pulled from the BASE_TABLE with specific where clause
#        criteria for the specific training sample option
#    4) using the final tmp table,
#        do a "select *" to get the basic reference data
#        use ExtractedTextSet.getExtractedTextSetForTable() to get their
#            extracted text
#        do select count(*) to get data set counts.
####################
START_DATE = "11/01/2019"      # earliest date for refs w/ cur pdftotext version
OLD_START_DATE = "01/01/2000"  # earliest date to get older refs from

# not used right now:
#LIT_TRIAGE_DATE = "10/31/2017" # when we switched to new lit triage
#END_DATE = "12/31/2019"                 # last date to get training data from

#----------------
OMIT_TEXT = "Omitted refs\n" + \
    "\tGOA loaded or only pm2gene indexed or MGI:Mice_in_references_only.\n" + \
    "\tExtracted text null or <500 chars.\n" + \
    "\tCreated >= %s" % OLD_START_DATE

BUILD_OMIT_TABLE = [ \
    # Tmp table of samples to omit from training sets since curators have not
    #     manually evaluated them (not good ground truth).
    # Currently, reasons to omit:
    # (1) articles "Indexed" by pm2gene & not selected/rejected by a group
    #     other than GO
    #
    # (2) created by the goa load and not selected/rejected by a group other
    #     than GO.
    #
    # In these cases, no curator has evaluated the paper, so we don't really
    #  know if these are relevant or not
    #
    # (3) articles marked as discard with MGI:Mice_in_references_only tag
    #
    # Also Omit papers w/o PDFs, or with null or short extracted text
    #    "body" sections.
'''
    create temporary table tmp_omit
    as
    select distinct r._refs_key, mgi.accid ID
    from bib_refs r join bib_workflow_status bs
        on (r._refs_key = bs._refs_key and bs.iscurrent=1 )
        join bib_status_view bsv on (r._refs_key = bsv._refs_key)
        left join bib_workflow_tag bt on (r._refs_key = bt._refs_key)
        join bib_workflow_relevance wr on (r._refs_key = wr._refs_key
                                                and wr.iscurrent=1)
        join bib_workflow_data bwd on (r._refs_key = bwd._refs_key
                            and bwd._extractedtext_key = 48804490) -- "body"
        join acc_accession mgi on (r._refs_key = mgi._object_key
                        and mgi._mgitype_key = 1 and mgi._logicaldb_key = 1
                        and mgi.prefixpart = 'MGI:' and mgi.preferred = 1)
    where 
    r.creation_date >= '%s'
    and
    (
        (   (   (bs._status_key = 31576673 and bs._group_key = 31576666 and 
                    bs._createdby_key = 1571 -- index for GO by pm2geneload
                )
                or r._createdby_key = 1575 -- created by littriage_goa
            )
            and           -- not selected/rejected by any other group
            (
                bsv.ap_status in    ('New', 'Not Routed', 'Routed')
            and bsv.gxd_status in   ('New', 'Not Routed', 'Routed')
            and bsv.tumor_status in ('New', 'Not Routed', 'Routed')
            and bsv.qtl_status in   ('New', 'Not Routed', 'Routed')
            and bsv.pro_status in   ('New', 'Not Routed', 'Routed')
            )
        )
        or
        (
            wr._relevance_key = 70594666        -- discard
            and bt._tag_key = 49170000          -- MGI:Mice_in_references_only
        )
        or
        (
            bwd.haspdf = 0
            or bwd.extractedtext is null
            or length(bwd.extractedtext) < 500
        )
    )
''' % (OLD_START_DATE),
'''
    create index tmp_idx1 on tmp_omit(_refs_key)
''',
]
#----------------
    # SQL to get papers that have been manually selected by one or more groups
SELECTED_TEXT = "Peer Reviewed Papers manually selected for curation\n" + \
    "\tCreated >= %s" % START_DATE
SELECTED_TMP_TBL = 'tmp_selected'
SELECTED_REFS_SQL = [ \
'''
    create temporary table %s
    as
    select distinct
        r._refs_key,
        mgid.accid ID,
        pmid.accid PMID,
        doid.accid DOID,
        to_char(r.creation_date, 'MM/DD/YYYY') as "creationDate",
        rcreator.login as "createdBy",
        r.date as "pubDate",
        r.year as "pubYear",
        typeTerm.term     as "refType",
        r.isreviewarticle as "isReview",
        rt.term          as "relevance",
        reluser.login    as "relevanceBy",
        suppTerm.term    as "suppStatus",
        bsv.ap_status    as "apStatus",
        bsv.gxd_status   as "gxdStatus", 
        bsv.go_status    as "goStatus", 
        bsv.tumor_status as "tumorStatus", 
        bsv.qtl_status   as "qtlStatus",
        bsv.pro_status   as "proStatus",
        r.journal, r.title, r.abstract
    from bib_refs r 
        join bib_status_view bsv on (r._refs_key = bsv._refs_key)
        join bib_workflow_relevance wr on (r._refs_key = wr._refs_key 
                                                and wr.iscurrent=1)
        join bib_workflow_data bwd on (r._refs_key = bwd._refs_key
                            and bwd._extractedtext_key = 48804490) -- "body"
        join voc_term suppTerm on (bwd._supplemental_key = suppTerm._term_key)
        join voc_term rt on (wr._relevance_key = rt._term_key)
        join voc_term typeTerm on (r._referencetype_key = typeTerm._term_key)
        join acc_accession mgid on
            (mgid._object_key = r._refs_key
             and mgid._mgitype_key = 1 and mgid._logicaldb_key = 1 -- MGI ID
             and mgid.prefixpart = 'MGI:' and mgid.preferred = 1)
        left join acc_accession pmid on
                                -- left joins since some papers don't seem
                                --  to have their pmid and doi in the db
            (pmid._object_key = r._refs_key and pmid._logicaldb_key=29 -- pubmed
             and pmid._mgitype_key=1 and pmid.preferred=1 )
        left join acc_accession doid on
            (doid._object_key = r._refs_key and doid._logicaldb_key=65 -- DOID
             and doid._mgitype_key=1 and doid.preferred=1 )
        join mgi_user rcreator on (r._createdby_key = rcreator._user_key)
        join mgi_user reluser on (wr._createdby_key = reluser._user_key)
    where -- Selected
    (   bsv.ap_status in ('Chosen', 'Indexed', 'Full-coded')
     or bsv.go_status in ('Chosen', 'Indexed', 'Full-coded')
     or bsv.gxd_status in ('Chosen', 'Indexed', 'Full-coded')
     or bsv.qtl_status in ('Chosen', 'Indexed', 'Full-coded')
     or bsv.tumor_status in ('Chosen', 'Indexed', 'Full-coded')
     or bsv.pro_status in ('Chosen', 'Indexed', 'Full-coded')
    )
    and not exists (select 1 from tmp_omit t where t._refs_key = r._refs_key)
    and r._referencetype_key = 31576687     -- Peer Reviewed Article
    and r.creation_date > '%s'
''' % (SELECTED_TMP_TBL, START_DATE),

'''create index tmp_idx_%s on %s(_refs_key)''' % \
                                        (SELECTED_TMP_TBL, SELECTED_TMP_TBL),
]
#----------------
    # SQL to get older papers
OLDREFS_TEXT = "Older Peer Reviewed Papers manually selected for GXD\n" + \
    "\tor manually selected/rejected for Tumor\n" + \
    "\tCreated >= %s and < %s" % (OLD_START_DATE, START_DATE)
OLDREFS_TMP_TBL = 'tmp_older'
OLDREFS_SQL = [ \
'''
    create temporary table %s
    as
    select distinct
        r._refs_key,
        mgid.accid ID,
        pmid.accid PMID,
        doid.accid DOID,
        to_char(r.creation_date, 'MM/DD/YYYY') as "creationDate",
        rcreator.login as "createdBy",
        r.date as "pubDate",
        r.year as "pubYear",
        typeTerm.term     as "refType",
        r.isreviewarticle as "isReview",
        rt.term          as "relevance",
        reluser.login    as "relevanceBy",
        suppTerm.term    as "suppStatus",
        bsv.ap_status    as "apStatus",
        bsv.gxd_status   as "gxdStatus", 
        bsv.go_status    as "goStatus", 
        bsv.tumor_status as "tumorStatus", 
        bsv.qtl_status   as "qtlStatus",
        bsv.pro_status   as "proStatus",
        r.journal, r.title, r.abstract
    from bib_refs r 
        join bib_status_view bsv on (r._refs_key = bsv._refs_key)
        join bib_workflow_relevance wr on (r._refs_key = wr._refs_key 
                                                and wr.iscurrent=1)
        join bib_workflow_data bwd on (r._refs_key = bwd._refs_key
                            and bwd._extractedtext_key = 48804490) -- "body"
        join voc_term suppTerm on (bwd._supplemental_key = suppTerm._term_key)
        join voc_term rt on (wr._relevance_key = rt._term_key)
        join voc_term typeTerm on (r._referencetype_key = typeTerm._term_key)
        join acc_accession mgid on
            (mgid._object_key = r._refs_key
             and mgid._mgitype_key = 1 and mgid._logicaldb_key = 1 -- MGI ID
             and mgid.prefixpart = 'MGI:' and mgid.preferred = 1)
        left join acc_accession pmid on
                                -- left joins since some papers don't seem
                                --  to have their pmid and doi in the db
            (pmid._object_key = r._refs_key and pmid._logicaldb_key=29 -- pubmed
             and pmid._mgitype_key=1 and pmid.preferred=1 )
        left join acc_accession doid on
            (doid._object_key = r._refs_key and doid._logicaldb_key=65 -- DOID
             and doid._mgitype_key=1 and doid.preferred=1 )
        join mgi_user rcreator on (r._createdby_key = rcreator._user_key)
        join mgi_user reluser on (wr._createdby_key = reluser._user_key)
    where -- Selected by GXD/Tumor or rejected by Tumor
    (   bsv.gxd_status   in ('Chosen', 'Indexed', 'Full-coded')
     or bsv.tumor_status in ('Chosen', 'Indexed', 'Full-coded', 'Rejected')
    )
    and not exists (select 1 from tmp_omit t where t._refs_key = r._refs_key)
    and r._referencetype_key = 31576687     -- Peer Reviewed Article
    and r.creation_date >= '%s'
    and r.creation_date < '%s'
''' % (OLDREFS_TMP_TBL, OLD_START_DATE, START_DATE),

'''create index tmp_idx_%s on %s(_refs_key)''' % \
                                        (OLDREFS_TMP_TBL, OLDREFS_TMP_TBL),
]
#----------------
    # SQL to get manually discarded papers
REJECTED_TEXT = "Peer Reviewed Papers manually discarded\n" + \
    "\tCreated >= %s" % START_DATE
REJECTED_TMP_TBL = 'tmp_rejected'
REJECTED_REFS_SQL = [ \
'''     -- Step 1:  get all fields into tmp_rejects1 except pmid and doi
        -- seems joining in acc tbl multiple times kills the query performance
    create temporary table tmp_rejects1
    as
    select distinct
        r._refs_key,
        mgid.accid ID,
--        pmid.accid PMID,
--        doid.accid DOID,
        to_char(r.creation_date, 'MM/DD/YYYY') as "creationDate",
        rcreator.login as "createdBy",
        r.date as "pubDate",
        r.year as "pubYear",
        typeTerm.term     as "refType",
        r.isreviewarticle as "isReview",
        rt.term          as "relevance",
        reluser.login    as "relevanceBy",
        suppTerm.term    as "suppStatus",
        bsv.ap_status    as "apStatus",
        bsv.gxd_status   as "gxdStatus", 
        bsv.go_status    as "goStatus", 
        bsv.tumor_status as "tumorStatus", 
        bsv.qtl_status   as "qtlStatus",
        bsv.pro_status   as "proStatus",
        r.journal, r.title, r.abstract
    from bib_refs r 
        join bib_status_view bsv on (r._refs_key = bsv._refs_key)
        join bib_workflow_relevance wr on (r._refs_key = wr._refs_key 
                                            and wr.iscurrent=1)
        join bib_workflow_data bwd on (r._refs_key = bwd._refs_key
                            and bwd._extractedtext_key = 48804490) -- "body"
        join voc_term suppTerm on (bwd._supplemental_key = suppTerm._term_key)
        join voc_term rt on (wr._relevance_key = rt._term_key)
        join voc_term typeTerm on (r._referencetype_key = typeTerm._term_key)
        join acc_accession mgid on
            (mgid._object_key = r._refs_key
             and mgid._mgitype_key = 1 and mgid._logicaldb_key = 1 -- MGI ID
             and mgid.prefixpart = 'MGI:' and mgid.preferred = 1)
        join mgi_user rcreator on (r._createdby_key = rcreator._user_key)
        join mgi_user reluser on (wr._createdby_key = reluser._user_key)
    where -- Rejected
    not exists (select 1 from tmp_omit t where t._refs_key = r._refs_key)
    and wr._relevance_key = 70594666        -- discard
    and wr._createdby_key != 1617       -- relevance_classifier
    and r._referencetype_key = 31576687     -- Peer Reviewed Article
    and r.creation_date > '%s'
''' % (START_DATE),

'''  -- Step 2:  join in pmid and doi into the final tmp table
    create temporary table %s
    as
    select t1.*, 
        pmid.accid PMID,
        doid.accid DOID
    from tmp_rejects1 t1        -- left joins since some papers don't seem
                                --  to have their pmid and doi in the db
        left join acc_accession pmid on
            (pmid._object_key = t1._refs_key and pmid._logicaldb_key=29 --pubmed
             and pmid._mgitype_key=1 and pmid.preferred=1 )
        left join acc_accession doid on
            (doid._object_key = t1._refs_key and doid._logicaldb_key=65 -- DOID
             and doid._mgitype_key=1 and doid.preferred=1 )
''' % (REJECTED_TMP_TBL),

'''create index tmp_idx_%s on %s(_refs_key)''' % \
                                        (REJECTED_TMP_TBL, REJECTED_TMP_TBL),
]
#----------------

def doCounts():
    '''
    Get counts of sample records from db and write them to stdout
    '''
    verbose("%s\nGetting dataset counts\n" % time.ctime())

    startTime = time.time()
    sys.stdout.write(time.ctime() + '\n')
    sys.stdout.write("Hitting database %s %s as mgd_public\n" % \
                                                    (args.host, args.db))

    selectCountSQL = 'select count(distinct _refs_key) as num from %s\n'

    db.sql(BUILD_OMIT_TABLE, 'auto')
    doCount(OMIT_TEXT, [selectCountSQL % "tmp_omit"])

    db.sql(SELECTED_REFS_SQL, 'auto')
    doCount(SELECTED_TEXT, [selectCountSQL % SELECTED_TMP_TBL])

    db.sql(REJECTED_REFS_SQL, 'auto')
    doCount(REJECTED_TEXT, [selectCountSQL % REJECTED_TMP_TBL])

    db.sql(OLDREFS_SQL, 'auto')
    doCount(OLDREFS_TEXT, [selectCountSQL % OLDREFS_TMP_TBL])

    verbose("Total time: %8.3f seconds\n\n" % (time.time()-startTime))
#-----------------------------------

def doCount(label, q  # list of sql stmts. last one being 'select count as num'
    ):
    results = db.sql(q, 'auto')
    num = results[-1][0]['num']
    sys.stdout.write("%7d\t%s\n" % (num, label))
#-----------------------------------

####################
def main():
####################
    db.set_sqlServer  (args.host)
    db.set_sqlDatabase(args.db)
    db.set_sqlUser    ("mgd_public")
    db.set_sqlPassword("mgdpub")

    if args.option == 'counts': doCounts()
    else: doSamples()

#-----------------------------------

def doSamples():
    '''
    Run SQL to get samples from DB and output them to stdout
    '''
    verbose("%s\nRetrieving reference set: %s\n" % (time.ctime(), args.option))
    verbose("Hitting database %s %s as mgd_public\n" % (args.host, args.db))
    startTime = time.time()

    # build the omit tmpTable - references to not retrieve
    verbose("Building OMIT table\n")
    db.sql(BUILD_OMIT_TABLE, 'auto')
    verbose("SQL time: %8.3f seconds\n\n" % (time.time()-startTime))

    # which subset to retrieve
    if args.option == "selected":
        tmpTableSQL  = SELECTED_REFS_SQL
        tmpTableName = SELECTED_TMP_TBL
        getExtractedText = True
    elif args.option == "rejected":
        tmpTableSQL  = REJECTED_REFS_SQL
        tmpTableName = REJECTED_TMP_TBL
        getExtractedText = True
    elif args.option == "older":
        tmpTableSQL  = OLDREFS_SQL
        tmpTableName = OLDREFS_TMP_TBL
        getExtractedText = False        # older refs have extText from older
                                        # pdftotext version in the db.
    else:
        sys.stderr.write("Invalid subset option '%s'\n" % args.option)
        exit(5)

    # build the tmpTable w/ the refs to retrieve
    verbose("Building %s table\n" % tmpTableName)
    tmpTableStart = time.time()
    db.sql(tmpTableSQL, 'auto')  # populate tmp tbl w/ desired references
    verbose("SQL time: %8.3f seconds\n\n" % (time.time()-tmpTableStart))

    # get the SQL result set from the tmpTable
    refRcds = db.sql(['select * from %s' % tmpTableName], 'auto')[-1]
    verbose("%d references retrieved\n" % (len(refRcds)))
    verbose("Total SQL time: %8.3f seconds\n\n" % (time.time()-startTime))

    if args.output == 'table':          # output table format
        fieldNames = [  '_refs_key',
                        'ID',
                        'PMID',
                        'DOID',
                        'creationDate',
                        'createdBy',
                        'pubDate',
                        'pubYear',
                        'refType',
                        'isReview',
                        'relevance',
                        'relevanceBy',
                        'suppStatus',
                        'apStatus',
                        'gxdStatus', 
                        'goStatus', 
                        'tumorStatus', 
                        'qtlStatus',
                        'proStatus',
                        'journal',
                        #'title',
                        #'abstract',
                        #'extractedText',
                    ]
        line = '|'.join(fieldNames) + '\n'
        sys.stdout.write(line)
        for r in refRcds:
            fields = [ str(r[fn]) for fn in fieldNames ]
            line = '|'.join(fields) + '\n'
            sys.stdout.write(line)

    elif args.output == 'samplefile':   # output sample file format

        # get their extracted text and join it to refRcds
        if getExtractedText:
            verbose("Getting extracted text\n")
            startTime = time.time()
            extTextSet = ExtractedTextSet.getExtractedTextSetForTable(db,
                                                                tmpTableName)
            extTextSet.joinRefs2ExtText(refRcds, allowNoText=False)
            verbose("%8.3f seconds\n\n" % (time.time()-startTime))

        # build Sample objects and put them in SampleSet
        outputSampleSet = MGIReference.SampleSet(sampleObjType=sampleObjType)
        startTime = time.time()
        verbose("constructing and writing samples:\n")
        for r in refRcds:
            sample = sqlRecord2ClassifiedSample(r)
            outputSampleSet.addSample(sample)

        # write SampleSet
        writeSamples(outputSampleSet)
        verbose("wrote %d samples:\n" % outputSampleSet.getNumSamples())
        verbose("%8.3f seconds\n\n" %  (time.time()-startTime))
    else:
        sys.stderr.write("Invalid output option: '%s'\n" % args.output)
        exit(5)
    return
#-----------------------------------

def writeSamples(sampleSet):
    sampleSet.setMetaItem('host', args.host)
    sampleSet.setMetaItem('db', args.db)
    sampleSet.setMetaItem('time', time.strftime("%Y/%m/%d-%H:%M:%S"))
    sampleSet.write(sys.stdout)
#-----------------------------------

def sqlRecord2ClassifiedSample(r,		# sql Result record
    ):
    """
    Encapsulates knowledge of Sample.setFields() field names
    """
    newR = {}
    newSample = sampleObjType()

    newR['_refs_key']    = str(r['_refs_key'])
    newR['ID']           = str(r['ID'])
    newR['PMID']         = str(r['PMID'])
    newR['DOID']         = str(r['DOID'])
    newR['creationDate'] = str(r['creationDate'])
    newR['createdBy']    = str(r['createdBy'])
    newR['pubDate']      = str(r['pubDate'])
    newR['pubYear']      = str(r['pubYear'])
    newR['refType']      = str(r['refType'])
    newR['isReview']     = str(r['isReview'])
    newR['relevance']    = str(r['relevance'])
    newR['relevanceBy']  = str(r['relevanceBy'])
    newR['suppStatus']   = str(r['suppStatus'])
    newR['apStatus']     = str(r['apStatus'])
    newR['gxdStatus']    = str(r['gxdStatus'])
    newR['goStatus']     = str(r['goStatus'])
    newR['tumorStatus']  = str(r['tumorStatus']) 
    newR['qtlStatus']    = str(r['qtlStatus'])
    newR['proStatus']    = str(r['proStatus'])
    newR['journal']      = str(r['journal'])
    newR['title']        = cleanUpTextField(r, 'title')
    newR['abstract']     = cleanUpTextField(r, 'abstract')
    newR['extractedText'] = cleanUpTextField(r, 'ext_text')
    if args.maxTextLength: newR['extractedText'] += '\n'

    return newSample.setFields(newR)
#-----------------------------------

def cleanUpTextField(rcd,
                    textFieldName,
    ):
    # in case we omit this text field during debugging, check if defined
    if rcd.has_key(textFieldName):      # 2to3 note: rcd is not a python dict,
                                        #  it has a has_key() method
        text = str(rcd[textFieldName])
    else: text = ''

    if args.maxTextLength:	# handy for debugging
        text = text[:args.maxTextLength]
        text = text.replace('\n', ' ')

    text = removeNonAscii(cleanDelimiters(text))
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

if __name__ == "__main__":
    if not (len(sys.argv) > 1 and sys.argv[1] == '--test'):
        main()
    else: 			# ad hoc test code
        sys.stderr.write('No automated tests defined\n')
