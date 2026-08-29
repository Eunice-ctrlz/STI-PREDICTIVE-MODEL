from django.db import models

from prediction_engine.models import RiskPrediction


class PredictionExplanation(models.Model):
    """
    An AI-generated explanation of one RiskPrediction.

    Stored rather than regenerated for three reasons: re-opening a result page
    should not re-bill a provider call, the explanation shown to a clinician
    should not silently change between views, and a clinical tool should be
    able to show exactly what AI-generated text was displayed at a given time.

    The relationship is one-to-one and CASCADE: an explanation has no meaning
    without its prediction. The dependency points this way only -- nothing in
    prediction_engine imports this model, so the ML path is unaffected by its
    presence or absence.
    """

    prediction = models.OneToOneField(
        RiskPrediction,
        on_delete=models.CASCADE,
        related_name='ai_explanation',
    )

    # Generated content, mirroring the API response fields.
    summary = models.TextField()
    what_this_means = models.TextField()
    important_considerations = models.JSONField(default=list)
    recommended_next_steps = models.JSONField(default=list)

    # Provenance. Recorded so a stored explanation can always be traced to the
    # provider and model that produced it. Never stores credentials.
    provider = models.CharField(max_length=50)
    model_identifier = models.CharField(max_length=100)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'AI prediction explanation'
        verbose_name_plural = 'AI prediction explanations'

    def __str__(self):
        return f'AI explanation for prediction {self.prediction_id} ({self.provider})'


# ---------------------------------------------------------------------------
# RAG knowledge base
#
# Chroma stores the vectors; these models store the *provenance*. The split
# matters because a vector store is not a system of record: it has no
# migrations, no referential integrity, no admin, and it can be deleted and
# rebuilt at any time. Everything needed to answer "where did this sentence
# come from?" and "what exactly is indexed right now?" therefore lives in the
# relational database, and Chroma holds only what it is good at -- fast
# approximate nearest-neighbour search over embeddings.
#
# This also keeps the system honest for a health tool: every retrieved
# sentence can be traced back to a specific uploaded document, and an
# out-of-date guideline can be deactivated without a re-index.
# ---------------------------------------------------------------------------


class KnowledgeDocument(models.Model):
    """
    A trusted source document that may ground AI explanations.

    Only documents from recognised health authorities belong here. The
    explanation layer is forbidden from inventing clinical facts (safety rule
    6), so the only way it may state a general educational claim is by
    grounding it in one of these.

    `active` exists so a superseded guideline can be withdrawn from retrieval
    immediately, without deleting the record that it was once used.
    """

    DOCUMENT_TYPES = [
        ('guideline', 'Clinical Guideline'),
        ('fact_sheet', 'Fact Sheet'),
        ('patient_info', 'Patient Information'),
        ('policy', 'Policy Document'),
        ('other', 'Other'),
    ]

    SOURCES = [
        ('who', 'World Health Organization'),
        ('cdc', 'US Centers for Disease Control and Prevention'),
        ('moh_kenya', 'Kenya Ministry of Health'),
        ('other', 'Other'),
    ]

    title = models.CharField(max_length=255)

    #: Publishing authority. Shown to the user beside any grounded claim, so
    #: it must be a body a clinician would actually recognise.
    source = models.CharField(max_length=30, choices=SOURCES, default='other')

    document_type = models.CharField(max_length=30, choices=DOCUMENT_TYPES, default='guideline')

    #: The original file. Kept after ingestion so the index can be rebuilt
    #: from scratch, and so a citation can be checked against the source.
    file = models.FileField(upload_to='knowledge/%Y/%m/')

    #: Free-text citation detail (edition, year, URL) shown with retrieved
    #: passages. Kept separate from `title` so citations stay stable even if
    #: the title is tidied up.
    citation = models.CharField(max_length=500, blank=True)

    #: False withdraws the document from retrieval without deleting it or
    #: touching the vector store.
    active = models.BooleanField(default=True)

    #: Ingestion bookkeeping, so `ingest_sti_documents` can skip unchanged
    #: files and report honestly on what is actually indexed.
    ingested_at = models.DateTimeField(null=True, blank=True)
    chunk_count = models.PositiveIntegerField(default=0)
    #: SHA-256 of the file contents. Re-ingestion is skipped when unchanged,
    #: which makes the command safe to run repeatedly.
    content_hash = models.CharField(max_length=64, blank=True, db_index=True)

    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = 'knowledge document'

    def __str__(self):
        return f'{self.title} ({self.get_source_display()})'

    @property
    def is_indexed(self) -> bool:
        return bool(self.ingested_at and self.chunk_count)

    def citation_label(self) -> str:
        """Short attribution string shown to the model and to the user."""
        return self.citation.strip() or f'{self.get_source_display()} - {self.title}'


class DocumentChunk(models.Model):
    """
    One retrievable passage of a KnowledgeDocument.

    Chunks are stored relationally as well as in Chroma for three reasons:

      * Chroma can be rebuilt from these rows without re-parsing PDFs.
      * A retrieval result carries only an id; the authoritative text and its
        source are looked up here, so a corrupted or stale vector entry
        cannot put unattributed text in front of a user.
      * Deactivating or deleting a document cascades here, which is what
        makes withdrawal of a guideline actually effective.

    `embedding_id` is the primary key used inside Chroma. It is generated
    deterministically from the document id and chunk index so re-ingestion
    overwrites rather than duplicates.
    """

    document = models.ForeignKey(
        KnowledgeDocument,
        on_delete=models.CASCADE,
        related_name='chunks',
    )

    #: Position within the document, used for stable ids and for ordering.
    chunk_index = models.PositiveIntegerField(default=0)

    chunk_text = models.TextField()

    #: Chroma's id for this chunk's vector.
    embedding_id = models.CharField(max_length=100, unique=True, db_index=True)

    #: Anything worth filtering or displaying later: page number, section
    #: heading, character offsets. Mirrored into Chroma metadata.
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['document', 'chunk_index']
        unique_together = ['document', 'chunk_index']
        indexes = [
            models.Index(fields=['document', 'chunk_index']),
        ]

    def __str__(self):
        return f'{self.document.title} [chunk {self.chunk_index}]'
