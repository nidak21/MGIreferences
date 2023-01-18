#!/usr/bin/env python3
#
# Library to support handling of reference records
# for experimenting with GXD secondary triage rules.
import re
from baseSampleDataLib import *
import figureText
#import utilsLib
from utilsLib import TextMapping, TextTransformer
#-----------------------------------

FIELDSEP     = '|'      # field separator when reading/writing sample fields
RECORDEND    = ';;'     # record ending str when reading/writing sample files

figConverterLegCloseWords75 = figureText.Text2FigConverter( \
                                            conversionType='legCloseWords',
                                            numWords=75)
#-----------------------------------
# Options for controlling the Age TextMapping reporting
REPORTBYREFERENCE = True       # True = report transformations by reference
                                # False= aggregate across whole corpus
REPORTFIXTRANSFORMS = False     # T/F report "fix" transformations
                                # (only applies if REPORTBYREFERENCE==True)
#CONTEXT = 30
CONTEXT = 210
#CONTEXT = 0

AgeMappings = [
    # Fix mappings: detect weird usages that would erroneously be mapped
    #  to mouse_age
    # by putting these "fix" mappings, 1st, if they match, none of the later
    # mappings will match (1st match wins), even if these don't change the text
    # BUT be careful about the order of these.
    # If two can overlap in their matching text, only the first one is applied.
    TextMapping('fix2',       # detect figure|table En (En is fig num)
                              # so En is not treated as eday
        r'\b(?:' +
            r'(?:figures?|fig[.s]?|tables?) e\d' +
        r')', lambda x: x,
        context=10),
    TextMapping('fix1',       # correct 'F I G U R E n' so it doesn't
                              # look like embryonic day "E n". "T A B L E" too
        r'\b(?:' +
            figureText.spacedOutRegex('figure') +
            r'|' + figureText.spacedOutRegex('table') +
        r')\b', lambda x: ''.join(x.split()), # funct to squeeze out spaces
        context=0),
    #TextMapping('fix3',       # so we don't match "injected ... blastocyst"
    #    r'(?:' +
    #        r'(?:(?:(?<!non-|not )inject)(?:\S|[ ]){1,25}?blastocysts?)' +
    #        r'|(?:blastocysts?(?:\S|[ ]){1,25}?inject)' +
    #    r')', lambda x: x,
    #    context=20),

    # Real age mappings
    TextMapping('dpc',
        r'\b(?:' +
            r'days?\spost(?:\s|-)?(?:conception|conceptus|coitum)' +
            r'|\d\d?dpc' +         # dpc w/ a digit or two before (no space)
            r'|dpc' +              # dpc as a word by itself
        r')\b', '__mouse_age', context=CONTEXT),

    TextMapping('eday',
        r'\b(?:' +
            r'embryonic\sdays?' + # spelled out, don't worry about numbers
            r'|[eg]d\s?\d' +       # ED or GD (embryonic|gestational)day+ 1 dig
            r'|[eg]d\s?1[0-9]' +   # ED or GD 2 digits: 10-19
            r'|[eg]d\s?20' +       # ED or GD 2 digits: 20

            r'|day\s\d[.]5' +      # day #.5 - single digit
            r'|day\s1\d[.]5' +     # day #.5 - 2 digits
            
            r'|\d[.]5\sdays?' +    # #.5 day - single digit
            r'|1\d[.]5\sdays?' +   # #.5 day - 2 digits

            r'|\d\sday\s(?:(?:mouse|mice)\s)?embryos?' +  # # day embryo - 1 dig
            r'|1\d\sday\s(?:(?:mouse|mice)\s)?embryos?' + # # day embryo - 2 dig

            # E1 E2 E3 are rarely used & often mean other things
            # E14 is often a cell line, not an age
            # Acceptable 2 decimal places:  .25 and .75 - regex: [.][27]5
            # Acceptable 1 decimal place:   .0 and .5   - regex: [.][05]
            r'|(?<![-])(?:' +     # not preceded by '-'
             r'e\d[.][27]5' +     # En  w/ 2 acceptable decimal places
             r'|e1\d[.][27]5' +   # E1n w/ 2 acceptable decimal places
             r'|e\s?\d[.][05]' +  # En or E n   w/ 1 acceptable dec place
             r'|e\s?1\d[.][05]' + # E1n or E 1n w/ 1 acceptable dec place
             r'|e\s?[4-9]' +      # E single digit
             r'|e\s1\d' +         # E (w/ space) double digits
             r'|e1[0123456789]' +  # E (no space) double digits - omit E14
             r'|e\s?20' +         # E double digits E20
            r')(?![.]\d|[%]|-bp|-ml|-mg)' + # not followed by decimal or
                                            #   % -bp -ml -mg

        r')\b', '__mouse_age', context=CONTEXT),

    TextMapping('ts',
        r'\b(?:' +
            r'theiler\sstages?' +
            r'|TS(?:\s|-)?[7-9]' +  # 1 digit, 0-6 not used or are other things
            r'|TS(?:\s|-)?[12]\d' +   # 2 digits
        r')\b', '__mouse_age', context=CONTEXT),
    TextMapping('ee',   # early embryo terms
                        # mesenchymal mesenchymes? ?
        r'\b(?:' +
            r'blastocysts?|blastomeres?|headfold|autopods?' +
            r'|embryonic\slysates?|embryo\slysates?' +
            r'|(?:(?:early|mid|late)(?:\s|-))?streak|morulae?|somites?' +
            r'|(?:limb(?:\s|-)?)buds?' +    # bud w/ limb in front
            r'|(?<!fin(?:\s|-))buds?' +     # bud w/o 'fin ' in front
            r'|(?:' +
                r'(?:[1248]|one|two|four|eight)(?:\s|-)cell\s' +
                r'(?:' +   # "embryo" or "stage" must come after [1248] cell
                    r'stages?|' +
                    r'(?:' +
                        r'(?:(?:mouse|mice|cloned)\s)?embryos?' +
                    r')' +
                r')' +
            r')' +
        r')\b', '__mouse_age', context=CONTEXT),
    TextMapping('developmental',   # "developmental" terms
        r'\b(?:' +
            r'(?:developmental|embryonic)\sstages?' +
            r'|(?:developmental|embryonic)\sages?' +
        r')\b', '__mouse_age', context=CONTEXT),
    TextMapping('fetus',   # fetus terms
        r'\b(?:' +
            r'fetus|fetuses' +
            r'|(?:fetal|foetal)(?!\s+(?:bovine|calf)\s+serum)' +
        r')\b', '__mouse_age', context=CONTEXT),
    ]

textTransformer_age = TextTransformer(AgeMappings)

#-----------------------------------

class RefSample (BaseSample):
    """
    Represents a reference from the db and its GXD status, extracted text, etc.
    classified or not.

    HAS: ID, text

    Provides various methods to preprocess a sample record
    (preprocess the text prior to vectorization)
    """
    sampleClassNames = ['No','Yes']
    y_positive = 1	# sampleClassNames[y_positive] is the "positive" class
    y_negative = 0	# ... negative

    # fields of a sample as an input/output record (as text), in order
    fieldNames = [ \
            'ID'           ,
            'text'         ,
            ]
    fieldSep  = FIELDSEP
    recordEnd = RECORDEND
    preprocessorsToReport = set()  # set of objects w/ a getReports() method
                                   #   to include in getPreprocessorReport()
    ageMatchReport = ''         # string w/ transformed age matches.
                                #  1 line per Reference per transformation

    # ---------------------------
    #@classmethod
    #def addPreprocessorToReport(cls, processor):
    #    cls.preprocessorsToReport.add(processor)

    @classmethod
    def getPreprocessorReport(cls):
        """ Return report text from preprocessor objects
        """
        # Age TextMapping report
        if REPORTBYREFERENCE:
            # get header line from standard report
            stdHdr = textTransformer_age.getReport().split('\n')[1]

            # add ID column
            cols = stdHdr.split('\t')
            hdr = '\t'.join(['ID'] + cols)  + '\n'
            output = hdr + cls.ageMatchReport
        else:   # get std report with counts across the whole corpus
            output = textTransformer_age.getReport()

        return output

    @classmethod
    def addToAgeMatchReport(cls, ID, line):
        cls.ageMatchReport += ID + '\t' + line + '\n'
    #----------------------
    # "preprocessor" functions.
    #  Each preprocessor should modify this sample and return itself
    #----------------------

    def standard(self):	# preprocessor
        '''
        "Standard" preprocessing steps we are using for production
        '''
        pass
        return self
    # ---------------------------

    def lower(self):        # preprocessor
        # lower case the text
        self.setField('text', self.getField('text').lower())
        return self
    # ---------------------------

    def rmNewLines(self):        # preprocessor
        # remove '\n' from the text to facilitate simple term searches
        self.setField('text', self.getField('text').replace('\n', ' '))
        return self
    # ---------------------------

    def figureTextLegCloseWords75(self):        # preprocessor
        # figure legends + 75 words around "figure" references in paragraphs
        self.setField('text', '\n\n'.join( \
            figConverterLegCloseWords75.text2FigText(self.getField('text'))))
        return self
    # ---------------------------

    def textTransform_age(self):                # preprocessor
        ''' Apply age text transformations
        '''
        tt = textTransformer_age
        self.setField('text', tt.transformText(self.getField('text')))

        if REPORTBYREFERENCE:
            # get textTransformer report lines for this ref,
            # add ref ID to each line and save these to cls.matchReport
            lines = tt.getReport().split('\n')

            for line in lines[2:]:  # add ref ID to the match report lines
                if line.strip() != '' and \
                    (REPORTFIXTRANSFORMS or not line.startswith('fix')):
                    self.addToAgeMatchReport(self.getID(), line)

            tt.resetMatches()       # clear the transformer matches for next ref
        return self
    # ---------------------------
# end class RefSample ------------------------

class ClassifiedRefSample (RefSample, ClassifiedSample):
    """
    A Reference that has been classified as selected/rejected by GXD
    """
    fieldNames = [ \
            'knownClassName',
            'ID',
            '_refs_key',
            'relevance',
            'confidence',
            'orig TP/FP',
            'GXD status',
            'journal',
            'text',
            ]
    extraInfoFieldNames = [ \
            'relevance',
            'confidence',
            'GXD status',
            'journal',
            ]
    #----------------------

# end class ClassifiedRefSample ------------------------

if __name__ == "__main__":
    pass
