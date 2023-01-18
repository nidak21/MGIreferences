What do we want?

a dataset of hand reviewed references:
    * skip refs w/ no text or text <500 chars
    * include refs with MGI:Mice_in_reference_only tag, include tag
    * refs selected by at least one curation group (Chosen, Indexed, Full-coded)
        - skip indexed by pm2gene and not selected by a group other than GO
        - skip created by goa load and not selected by a group other than GO
    * refs manually set to discard
    * refs rejected by all groups (maybe ignore qtl?)

Want representation of the db (not a dataset w/ Yes/No yet)
    * IDs (MGI, pubmed, DOI)
    * _refs_key
    * creation date
    * publication date
    * publication year
    * refType

    * discardKeep      rt.term (discard/keep)
    * isReview         r.isreviewarticle
    * suppStatus       suppTerm.term
    * bsv.ap_status
    * bsv.gxd_status
    * bsv.go_status
    * bsv.tumor_status
    * bsv.qtl_status
    * bsv.pro_status
    * miceOnlyInRefs

    * journal
    * title
    * abstract
    * full extracted text (re-extracted w/ latest pdftotext) - need date
        - 1st step - get w/o text
        - verify counts
        - get text from db for refs w/ extracted text after new pdftotext
        - do pdftotext extraction for earlier papers
