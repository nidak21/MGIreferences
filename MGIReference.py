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
import figureText
import featureTransform
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
urls_re      = re.compile(r'\b(?:https?://|www[.]|doi)\S*',re.IGNORECASE)
token_re     = re.compile(r'\b([a-z_]\w+)\b',re.IGNORECASE)

stemmer = None		# see preprocessor below
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
            'ID'            , # MGI ID
            'PMID'          ,
            'DOI'           ,
            '_refs_key'     , # MGI db reference key
            'creationDate'  , # MGI db creation date
            'date'          , # pub date
            'year'          , # pub year
            'refType'       ,
            'discardKeep'   ,
            'isReview'      ,
            'suppStatus'    ,
            'apStatus'      ,
            'gxdStatus'     ,
            'goStatus'      ,
            'tumorStatus'   ,
            'qtlStatus'     ,
            'proStatus'     ,
            'miceOnlyInRefs',
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

    def figureTextLegends(self):	# preprocessor
        # just figure legends
        self.setExtractedText('\n\n'.join( \
                figConverterLegends.text2FigText(self.getExtractedText())))
        return self
    # ---------------------------

    def figureTextLegParagraphs(self):	# preprocessor
        # figure legends + paragraphs discussing figures
        self.setExtractedText('\n\n'.join( \
            figConverterLegParagraphs.text2FigText(self.getExtractedText())))
        return self
    # ---------------------------

    def figureTextLegCloseWords50(self):	# preprocessor
        # figure legends + 50 words around "figure" references in paragraphs
        self.setExtractedText('\n\n'.join( \
            figConverterLegCloseWords50.text2FigText(self.getExtractedText())))
        return self
    # ---------------------------

    def featureTransform(self):		# preprocessor
        self.setTitle( featureTransform.transformText(self.getTitle()) )
        self.setAbstract( featureTransform.transformText(self.getAbstract()) )
        self.setExtractedText( featureTransform.transformText( \
                                                self.getExtractedText()) )
        return self
    # ---------------------------

    def removeURLsCleanStem(self):	# preprocessor
        '''
        Remove URLs and punct, lower case everything,
        Convert '-/-' to 'mut_mut',
        Keep tokens that start w/ letter or _ and are 2 or more chars.
        Stem,
        Replace \n with spaces
        '''
        # This is currently the only preprocessor that uses a stemmer.
        # Would be clearer to import and instantiate one stemmer above,
        # BUT that requires nltk (via anaconda) to be installed on each
        # server we use. This is currently not installed on our linux servers
        # By importing here, we can use RefSample in situations where we don't
        # call this preprocessor, and it will work on our current server setup.
        global stemmer
        if not stemmer:
            import nltk.stem.snowball as nltk
            stemmer = nltk.EnglishStemmer()
        #------
        def _removeURLsCleanStem(text):
            output = ''
            for s in urls_re.split(text): # split and remove URLs
                s = featureTransform.transformText(s).lower()
                for m in token_re.finditer(s):
                    output += " " + stemmer.stem(m.group())
            return  output
        #------

        self.setTitle( _removeURLsCleanStem( self.getTitle()) )
        self.setAbstract( _removeURLsCleanStem( self.getAbstract()) )
        self.setExtractedText( _removeURLsCleanStem( self.getExtractedText()) )
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
