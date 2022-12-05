#!/usr/bin/env python3
'''
  Purpose:
           run sql to get lit triage relevance training set
           (minor) Data transformations include:
            replacing non-ascii chars with ' '
            replacing FIELDSEP and RECORDSEP chars in the doc text w/ ' '

  Outputs:      Delimited file to stdout
                See sampleDataLib.ClassifiedSample for output format
'''
#-----------------------------------
import sys
import os
import string
import re
import time
import argparse
import db
import sampleDataLib
from utilsLib import removeNonAscii
import ExtractedTextSet
#-----------------------------------

sampleObjType = sampleDataLib.PrimTriageClassifiedSample

# for the Sample output file
outputSampleSet = sampleDataLib.ClassifiedSampleSet(sampleObjType=sampleObjType)
RECORDEND    = sampleObjType.getRecordEnd()
FIELDSEP     = sampleObjType.getFieldSep()
#-----------------------------------

def getArgs():

    parser = argparse.ArgumentParser( \
        description='Get littriage relevance training samples, write to stdout')

    parser.add_argument('--test', dest='test', action='store_true',
        required=False,
        help="just run ad hoc test code")

    parser.add_argument('option', action='store', default='counts',
        choices=['discard_after', 'keep_after', 'keep_before',
                    'keep_tumor', 'test_2020', 'counts'],
        help='which subset of training samples to get or "counts" (default)')

    parser.add_argument('-l', '--limit', dest='nResults',
        required=False, type=int, default=0, 		# 0 means ALL
        help="limit results to n references. Default is no limit")

    parser.add_argument('--textlength', dest='maxTextLength',
        type=int, required=False, default=None,
        help="only include the 1st n chars of text fields (for debugging)")

    parser.add_argument('--norestrict', dest='restrictArticles',
        action='store_false', required=False,
        help="include all articles, default: skip review and non-peer reviewed")

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
LIT_TRIAGE_DATE = "10/31/2017"		# when we switched to new lit triage
START_DATE = "1/01/2017" 		# earliest date for refs to get
                                        #  before lit Triage
TUMOR_START_DATE = "07/01/2013"		# date to get add'l tumor papers from
END_DATE = "12/31/2019"                 # last date to get training data from

#----------------
OMIT_TEXT = "Omitted refs\n" + \
    "\t(GOA loaded or only pm2gene indexed or MGI:Mice_in_references_only)"
BUILD_OMIT_TABLE = [ \
    # Tmp table of samples to omit.
    # Currently, reasons to omit:
    # (1) articles "indexed" by pm2gene & not selected by a group other than GO
    #
    # (2) created by the goa load and not selected by a group other than GO.
    # In these cases, no curator has selected the paper, so we don't really
    #  know if these are relevant (not good ground truth)
    #
    # (3) articles marked as discard with MGI:Mice_in_references_only tag
    # Since these articles are discarded for a different reason, and they
    #  will not go through relevance classification, it seems we should not
    #  train on them.
'''
    create temporary table tmp_omit
    as
    select r._refs_key, a.accid pubmed
    from bib_refs r join bib_workflow_status bs
        on (r._refs_key = bs._refs_key and bs.iscurrent=1 )
        join bib_status_view bsv on (r._refs_key = bsv._refs_key)
        left join bib_workflow_tag bt on (r._refs_key = bt._refs_key)
        join bib_workflow_relevance wr on (r._refs_key = wr._refs_key
                                                and wr.iscurrent=1)
        join acc_accession a
        on (a._object_key = r._refs_key and a._logicaldb_key=29 -- pubmed
            and a._mgitype_key=1 )
    where 
        (   (   (bs._status_key = 31576673 and bs._group_key = 31576666 and 
                    bs._createdby_key = 1571 -- index for GO by pm2geneload
                )
                or r._createdby_key = 1575 -- created by littriage_goa
            )
            and           -- not selected by any other group
            (
                bsv.ap_status in ('Not Routed', 'Rejected')
            and bsv.gxd_status in ('Not Routed', 'Rejected')
            and bsv.tumor_status in ('Not Routed', 'Rejected')
            and bsv.qtl_status in ('Not Routed', 'Rejected')
            and r.creation_date >= '%s'
            )
        )
        or
        (
            wr._relevance_key = 70594666        -- discard
            and bt._tag_key = 49170000          -- MGI:Mice_in_references_only
        )
''' % (START_DATE),
'''
    create index tmp_idx1 on tmp_omit(_refs_key)
''',
]
#----------------
BUILD_BASE_TABLE = [ \
'''
    create temporary table tmp_refs
    as
    select distinct r._refs_key, r.creation_date
    from bib_refs r join bib_workflow_data bd on (r._refs_key = bd._refs_key)
    where r._createdby_key != 1609          -- not littriage_discard user
       and bd.extractedtext is not null
       and not exists (select 1 from tmp_omit t where t._refs_key = r._refs_key)
''',
'''
    create index tmp_idx2 on tmp_refs(_refs_key)
''',
    # this index is important for speed since bib_refs does not have an index on
    #  creation_date
'''
    create index tmp_idx3 on tmp_refs(creation_date)
''',
]
#----------------
FINAL_TMP_TABLE_SQL =  \
'''
    create temporary table %s
    as
    select distinct r._refs_key,
        rt.term as knownClassName,
        r.year,
        to_char(r.creation_date, 'MM/DD/YYYY') as "creation_date",
        r.isreviewarticle,
        typeTerm.term as ref_type,
        'ignore supp term' as supp_status,
        -- suppTerm.term as supp_status,
        r.journal, r.title, r.abstract,
        a.accid pubmed,
        bsv.ap_status,
        bsv.gxd_status, 
        bsv.go_status, 
        bsv.tumor_status, 
        bsv.qtl_status
    from bib_refs r join tmp_refs tr on (r._refs_key = tr._refs_key)
        join bib_workflow_data bd on (r._refs_key = bd._refs_key)
        join bib_status_view bsv on (r._refs_key = bsv._refs_key)
        -- join voc_term suppTerm on (bd._supplemental_key = suppTerm._term_key)
        -- (was originally including supp status term for analysis, but
        --  sometimes there were duplicate status rcds in bib_workflow_data,
        --  so I'm skipping this for now)
        join bib_workflow_relevance wr on (r._refs_key = wr._refs_key 
                                                and wr.iscurrent=1)
        join voc_term rt on (wr._relevance_key = rt._term_key)
        join voc_term typeTerm on (r._referencetype_key = typeTerm._term_key)
        join acc_accession a on
             (a._object_key = r._refs_key and a._logicaldb_key=29 -- pubmed
              and a._mgitype_key=1 and a.preferred=1 )
'''
RESTRICT_REF_TYPE = \
'''
    and r._referencetype_key=31576687 -- peer reviewed article
    and r.isreviewarticle != 1
'''
#----------------
# Dict of where clause components for specific query options,
#  these should be non-overlapping result sets
WHERE_CLAUSES = { \
'discard_after' :
    '''
    where -- discard_after
    wr._relevance_key = 70594666        -- discard
        -- Note: using rt.term = 'discard', I could not get the query to return
    and tr.creation_date > '%s' -- After lit triage release
    and tr.creation_date <= '%s' -- before end date
    ''' % (LIT_TRIAGE_DATE, END_DATE),
'keep_after' :
    '''
    where -- keep_after
    (bsv.ap_status in ('Chosen', 'Indexed', 'Full-coded')
     or bsv.go_status in ('Chosen', 'Indexed', 'Full-coded')
     or bsv.gxd_status in ('Chosen', 'Indexed', 'Full-coded')
     or bsv.qtl_status in ('Chosen', 'Indexed', 'Full-coded')
     or bsv.tumor_status in ('Chosen', 'Indexed', 'Full-coded')
    )
    and tr.creation_date > '%s' -- After lit triage release
    and tr.creation_date <= '%s' -- before end date
    ''' % (LIT_TRIAGE_DATE, END_DATE),
'keep_before' :
    '''
    where -- keep_before
    (bsv.ap_status in ('Chosen', 'Indexed', 'Full-coded')
     or bsv.go_status in ('Chosen', 'Indexed', 'Full-coded')
     or bsv.gxd_status in ('Chosen', 'Indexed', 'Full-coded')
     or bsv.qtl_status in ('Chosen', 'Indexed', 'Full-coded')
     or bsv.tumor_status in ('Chosen', 'Indexed', 'Full-coded')
    )
    and tr.creation_date >= '%s' -- after start date
    and tr.creation_date <= '%s' -- before lit triage release
    ''' % (START_DATE, LIT_TRIAGE_DATE, ),
'keep_tumor' :
    '''
    where -- keep_tumor
     bsv.tumor_status in ('Chosen', 'Indexed', 'Full-coded')
     and tr.creation_date >= '%s' -- after tumor start date
     and tr.creation_date <= '%s' -- before start date
    ''' % (TUMOR_START_DATE, START_DATE, ),
'test_2020' :
    '''
    where -- test set of 2020 refs
    tr.creation_date > '%s'          -- After end date
    and tr.creation_date <= '12/31/2020' -- before end of 2020
    and
    (
        (wr._relevance_key = 70594666)        -- discard
        or
        (bsv.ap_status in ('Chosen', 'Indexed', 'Full-coded')
         or bsv.go_status in ('Chosen', 'Indexed', 'Full-coded')
         or bsv.gxd_status in ('Chosen', 'Indexed', 'Full-coded')
         or bsv.qtl_status in ('Chosen', 'Indexed', 'Full-coded')
         or bsv.tumor_status in ('Chosen', 'Indexed', 'Full-coded')
        )
    )
    ''' % (END_DATE),
}	# end WHERE_CLAUSES
#-----------------------------------

def doCounts():
    '''
    Get counts of sample records from db and write them to stdout
    '''
    sys.stdout.write(time.ctime() + '\n')
    sys.stdout.write("Hitting database %s %s as mgd_public\n" % \
                                                    (args.host, args.db))
    sys.stdout.write(getRestrictedArticleText())

    selectCountSQL = 'select count(distinct _refs_key) as num from %s\n'

    db.sql(BUILD_OMIT_TABLE, 'auto')
    db.sql(BUILD_BASE_TABLE, 'auto')

    doCount(OMIT_TEXT, [selectCountSQL % "tmp_omit"])

    tmpTableName, finalTmpTableSQL = buildFinalTmpTableSQL('discard_after')
    doCount("Discard after: %s - %s" % (LIT_TRIAGE_DATE, END_DATE),
                        finalTmpTableSQL + [selectCountSQL % tmpTableName])

    tmpTableName, finalTmpTableSQL = buildFinalTmpTableSQL('keep_after')
    doCount("Keep after: %s - %s" % (LIT_TRIAGE_DATE, END_DATE),
                        finalTmpTableSQL + [selectCountSQL % tmpTableName])

    tmpTableName, finalTmpTableSQL = buildFinalTmpTableSQL('keep_before')
    doCount("Keep before: %s - %s" % (START_DATE, LIT_TRIAGE_DATE),
                        finalTmpTableSQL + [selectCountSQL % tmpTableName])

    tmpTableName, finalTmpTableSQL = buildFinalTmpTableSQL('keep_tumor')
    doCount("Tumor papers: %s - %s" % (TUMOR_START_DATE, START_DATE),
                        finalTmpTableSQL + [selectCountSQL % tmpTableName])

    tmpTableName, finalTmpTableSQL = buildFinalTmpTableSQL('test_2020')
    doCount("Test set from 2020" ,
                        finalTmpTableSQL + [selectCountSQL % tmpTableName])
#-----------------------------------

def doCount(label, q  # list of sql stmts. last one being 'select count as num'
    ):
    results = db.sql(q, 'auto')
    num = results[-1][0]['num']
    sys.stdout.write("%7d\t%s\n" % (num, label))
#-----------------------------------

def getRestrictedArticleText():
    if args.restrictArticles:
        text = "Omitting review and non-peer reviewed articles\n"
    else:
        text = "Including review and non-peer reviewed articles\n"
    return text
#-----------------------------------

def buildFinalTmpTableSQL(queryKey):
    """
    Assemble SQL statements to build final tmp table with the references from
        the desired queryKey
    Return tmpTableName and list of SQL stmts
    """
    if args.restrictArticles: restrict = RESTRICT_REF_TYPE
    else: restrict = ''

    if args.nResults > 0: limitSQL = "\nlimit %d\n" % args.nResults
    else: limitSQL = ''

    finalTmpTableName = 'tmp_' + queryKey

    finalTmpTableSQL = (FINAL_TMP_TABLE_SQL % finalTmpTableName) + \
                        WHERE_CLAUSES[queryKey] + restrict + limitSQL

    buildIndexSQL = 'create index tmp_idx_%s on %s(_refs_key)' % \
                                            (queryKey, finalTmpTableName)

    return finalTmpTableName, [finalTmpTableSQL, buildIndexSQL]
#-----------------------------------

####################
def main():
####################
    db.set_sqlServer  (args.host)
    db.set_sqlDatabase(args.db)
    db.set_sqlUser    ("mgd_public")
    db.set_sqlPassword("mgdpub")
    startTime = time.time()

    if args.option == 'counts': doCounts()
    else: doSamples()

    verbose("Total time: %8.3f seconds\n\n" % (time.time()-startTime))
#-----------------------------------

def doSamples():
    '''
    Run SQL to get samples from DB and output them to stdout
    '''
    verbose("Hitting database %s %s as mgd_public\n" % (args.host, args.db))
    verbose(getRestrictedArticleText())
    verbose("Retreiving reference set: %s\n" % args.option)
    startTime = time.time()

    # build initial tmp tables
    db.sql(BUILD_OMIT_TABLE, 'auto')
    db.sql(BUILD_BASE_TABLE, 'auto')

    # build final tmp tbl with the desired references
    tmpTableName, finalTmpTableSQL = buildFinalTmpTableSQL(args.option)
    db.sql(finalTmpTableSQL, 'auto')

    # get the result set
    refRcds = db.sql(['select * from %s' % tmpTableName], 'auto')[-1]
    verbose("%d references retrieved\n" % (len(refRcds)))
    verbose("SQL time: %8.3f seconds\n\n" % (time.time()-startTime))

    # get their extracted text and join it to refRcds
    verbose("Getting extracted text\n")
    startTime = time.time()
    extTextSet = ExtractedTextSet.getExtractedTextSetForTable(db, tmpTableName)
    extTextSet.joinRefs2ExtText(refRcds, allowNoText=True)
    verbose("%8.3f seconds\n\n" % (time.time()-startTime))

    # build Sample objects and write SampleSet
    global outputSampleSet
    startTime = time.time()
    verbose("constructing and writing samples:\n")
    for r in refRcds:
        sample = sqlRecord2ClassifiedSample(r)
        outputSampleSet.addSample(sample)

    writeSamples(outputSampleSet)
    verbose("wrote %d samples:\n" % outputSampleSet.getNumSamples())
    verbose("%8.3f seconds\n\n" %  (time.time()-startTime))
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
    Encapsulates knowledge of ClassifiedSample.setFields() field names
    """
    newR = {}
    newSample = sampleObjType()

    newR['knownClassName']= str(r['knownClassName'])
    newR['ID']            = str(r['pubmed'])
    newR['creationDate']  = str(r['creation_date'])
    newR['year']          = str(r['year'])
    newR['journal']       = '_'.join(str(r['journal']).split(' '))
    newR['title']         = cleanUpTextField(r, 'title')
    newR['abstract']      = cleanUpTextField(r, 'abstract')
    newR['extractedText'] = cleanUpTextField(r, 'ext_text')
    if args.maxTextLength: newR['extractedText'] += '\n'
    newR['isReview']      = str(r['isreviewarticle'])
    newR['refType']       = str(r['ref_type'])
    newR['suppStatus']    = str(r['supp_status'])
    newR['apStatus']      = str(r['ap_status'])
    newR['gxdStatus']     = str(r['gxd_status'])
    newR['goStatus']      = str(r['go_status'])
    newR['tumorStatus']   = str(r['tumor_status']) 
    newR['qtlStatus']     = str(r['qtl_status'])

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
        if True:	# debug SQL
            for query in WHERE_CLAUSES.keys():
                tmpTableName, finalTmpTableSQL = buildFinalTmpTableSQL(query)
                print('||'.join(finalTmpTableSQL))
                print()
