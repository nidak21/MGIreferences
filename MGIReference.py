#!/usr/bin/env python3
#
# Library to support handling of MGI lit records (training samples or
#  samples to predict)
#
# There are automated unit tests for this module:
#   cd test
#   python test_sampleDataLib.py -v
#
import sys
import os.path
import string
import re
from copy import copy
from baseSampleDataLib import *
import utilsLib
#import figureText
#import featureTransform
#-----------------------------------
#
# Naming conventions:
#  * use camelCase for most things
#  * but stick to sklearn convention for y_*  which are the indexes of
#      sample classification names, e.g., 'discard', 'keep'
#  * use "class" or "classname" to mean the sample classification names
#  * this is confusing with python "classes"
#  * so try to use "python class" or "object type" for these
#-----------------------------------

FIELDSEP     = '|'      # field separator when reading/writing sample fields
RECORDEND    = ';;'     # record ending str when reading/writing sample files

#-----------------------------------
# Regex's sample preprocessors
#urls_re      = re.compile(r'\b(?:https?://|www[.]|doi)\S*',re.IGNORECASE)
#token_re     = re.compile(r'\b([a-z_]\w+)\b',re.IGNORECASE)

#stemmer = None		# see preprocessor below
#-----------------------------------

class MGIReference (BaseSample):
    """
    Represents a reference sample (article) from MGI

    HAS: ID, title, abstract, extracted text, etc.

    Provides various methods to preprocess a sample record
    (preprocess the text prior to vectorization)
    """
    # fields of a sample as an input/output record (as text), in order
    fieldNames = [ \
            '_refs_key'     , # MGI db reference key
            'ID'            , # MGI ID
            'PMID'          ,
            'DOID'          ,
            'creationDate'  , # MGI db creation date
            'createdBy'     , 
            'pubDate'       , # pub date
            'pubYear'       , # pub year
            'refType'       ,
            'isReview'      ,
            'relevance'     ,
            'relevanceBy'   ,
            'suppStatus'    ,
            'apStatus'      ,
            'gxdStatus'     ,
            'goStatus'      ,
            'tumorStatus'   ,
            'qtlStatus'     ,
            'proStatus'     ,
            'journal'       ,
            'title'         ,
            'abstract'      ,
            'extractedText' ,
            ]
    fieldSep  = FIELDSEP
    recordEnd = RECORDEND
    #----------------------

    def constructDoc(self):
        return '\n'.join([self.getTitle(), self.getAbstract(),
                                                    self.getExtractedText()])

    def setExtractedText(self, t): self.values['extractedText'] = t
    def getExtractedText(self,  ): return self.values['extractedText']

    def setAbstract(self, t): self.values['abstract'] = t
    def getAbstract(self,  ): return self.values['abstract']

    def setTitle(self, t): self.values['title'] = t
    def getTitle(self,  ): return self.values['title']

    #----------------------
    # "preprocessor" functions.
    #  Each preprocessor should modify this sample and return itself
    #----------------------

    def rejectIfNoText(self):		# preprocessor
        '''
        set to reject if extracted text is missing or very short
        '''
        if len(self.getExtractedText()) < 500:
            self.setReject(True, reason="extracted text is < 500 chars")
        return self
    # ---------------------------

    def removeURLs(self):		# preprocessor
        '''
        Remove URLs, lower case everything,
        '''
        self.setTitle( utilsLib.removeURLsLower( self.getTitle()) )
        self.setAbstract( utilsLib.removeURLsLower( self.getAbstract() ) )
        self.setExtractedText(utilsLib.removeURLsLower(self.getExtractedText()))
        return self
    # ---------------------------

    def tokenPerLine(self):		# preprocessor
        """
        Convert text to have one alphanumeric token per line,
            removing punctuation.
        Makes it easier to examine the tokens/features
        """
        self.setTitle( utilsLib.tokenPerLine( self.getTitle()) )
        self.setAbstract( utilsLib.tokenPerLine( self.getAbstract()) )
        self.setExtractedText( utilsLib.tokenPerLine( self.getExtractedText()) )
        return self
    # ---------------------------

    def truncateText(self):		# preprocessor
        """ for debugging, so you can see a sample record easily"""
        
        self.setTitle( self.getTitle()[:10].replace('\n',' ') )
        self.setAbstract( self.getAbstract()[:20].replace('\n',' ') )
        self.setExtractedText(self.getExtractedText()[:20].replace('\n',' ') \
                                                                        +'\n')
        return self
    # ---------------------------

    def removeText(self):		# preprocessor
        """ for debugging, so you can see a sample record easily"""
        
        self.setTitle( self.getTitle()[:10].replace('\n',' ') )
        self.setAbstract( 'abstract...' )
        self.setExtractedText( 'extracted text...\n' )
        return self
    # ---------------------------

    def replaceText(self):		# preprocessor
        """ for debugging, replace the extracted text with text from a file
            Filename is <ID>.new.txt
        """
        fileName = self.getID() + ".new.txt"
        if os.path.isfile(fileName):
            newText = open(fileName, 'r').read()
            self.setExtractedText(newText)
        return self
    # ---------------------------
# end class MGIReference ------------------------

if __name__ == "__main__":
    pass
