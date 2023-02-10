#!/usr/bin/env python3
'''
  Purpose:
           Read a MGIReferences sample file, and for samples that have empty
           extracted text, locate their PDF and extract the text from it, and
           save that as their extracted text in the sample file.
           
           No changes to the text except for removal of field separators,
           record endings, and non-ascii characters.

  Outputs:      Delimited file to specified output file.
                See MGIReference.Sample for output format
'''
import sys
import os
import time
import argparse
import subprocess
import unittest
import db
import Pdfpath
#import extractedTextSplitter
import MGIReference as sampleLib
from utilsLib import removeNonAscii

#-----------------------------------

sampleObjType = sampleLib.MGIReference

# for the Sample output file
RECORDEND    = sampleObjType.getRecordEnd()
FIELDSEP     = sampleObjType.getFieldSep()

MINTEXTLENGTH = 500     # skip refs with extracted text shorter than this

LONGTIME = 60           # num of seconds. If a pdf extraction takes longer
                        #   than this, report it.
#-----------------------------------

def getArgs():

    parser = argparse.ArgumentParser( \
        description='Get extracted text from PDFs.')

#    parser.add_argument('option', action='store', default='counts',
#        choices=['routed', 'notRoutedKeep', 'notRoutedDiscard', 'ids','test'],
#        help='get samples, IDs from stdin, or just run automated tests')

    parser.add_argument('sampleFile', action='store', 
        help='the sample file to read and update.')

#    parser.add_argument('--frompdf', dest='fromPDF', action='store_true',
#        required=False,
#        help="extract text from the archived PDFs instead of from db")

    parser.add_argument('-l', '--limit', dest='limit',
        required=False, type=int, default=0, 		# 0 means ALL
        help="only extract text for up to n references. Default is no limit")

#    parser.add_argument('--textlength', dest='maxTextLength',
#        type=int, required=False, default=None,
#        help="only include the 1st n chars of text fields (for debugging)")

    parser.add_argument('-q', '--quiet', dest='verbose', action='store_false',
        required=False, help="skip helpful messages to stderr")

    return parser.parse_args()
#-----------------------------------

args = getArgs()

#-----------------------------------

def main():

    startTime = time.time()

    sampleSet = sampleLib.SampleSet(sampleObjType).read(args.sampleFile)

    numAlready   = 0    # num of samples that already have extracted text
    numAttempted = 0    # num of samples that we attempted to extracted text for
    numExtracted = 0    # num of samples that we successfully extracted text for
    numErrors    = 0    # num of samples with errors during text extraction

    for sample in sampleSet.getSamples():
        if len(sample.getField('extractedText')) > 0:
            numAlready += 1
        else:
            mgiID = sample.getField('ID')
            numAttempted += 1
            verbose("Extracting text for %s\n" % mgiID)

            pdfStart = time.time()
            text, error = getText4Ref_fromPDF(mgiID)
            elapsedTime = time.time() - pdfStart

            if elapsedTime > LONGTIME:
                verbose("%s extraction took %8.3f seconds\n" \
                                                    % (mgiID, elapsedTime) )
            if error:
                verbose("Error extracting text for  %s:\n%s" % (mgiID, error))
                numErrors += 1
            else:
                text = cleanUpTextField(text)
                sample.setField('extractedText', text)
                numExtracted += 1
        if numAttempted == args.limit: break

    sampleSet.write(args.sampleFile)
    verbose('\n')
    verbose("wrote %d samples to '%s'\n" % (sampleSet.getNumSamples(),
                                            args.sampleFile))
    verbose("Samples seen with text already: %d\n" % numAlready)
    verbose("Samples with new text added: %d\n" % numExtracted)
    verbose("Samples with text extraction errors: %d\n" % numErrors)
    verbose("%8.3f seconds\n\n" %  (time.time()-startTime))
#-----------------------------------

def getText4Ref_fromPDF(mgiID):
    """ Return (text, error)
        text = extracted text (string) from the PDF.
            for the specified MGI ID
        error = None or an error message if the text could not be extracted.
    """
    PDF_STORAGE_BASE_PATH = '/data/littriage'
    prefix, numeric = mgiID.split(':')
    filePath = os.path.join(Pdfpath.getPdfpath(PDF_STORAGE_BASE_PATH,mgiID),
                                                            numeric + '.pdf')
    text, error = extractTextFromPdf(filePath)

    return text, error
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

def cleanUpTextField(text):

    if text == None:
        text = ''
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
        sys.stdout.write(text)
        sys.stdout.flush()
#-----------------------------------

def doAutomatedTests():

    sys.stdout.write("No automated tests at this time\n")
    return

    sys.stdout.write("Running automated unit tests...\n")
    unittest.main(argv=[sys.argv[0], '-v'],)

class MyTests(unittest.TestCase):
    def test_getText4Ref(self):
        t = getText4Ref('11943') # no text
        self.assertEqual(t, '')

#-----------------------------------
if __name__ == "__main__":
    main()
