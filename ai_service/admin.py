from django.contrib import admin

from .models import DocumentChunk, KnowledgeDocument, PredictionExplanation


@admin.register(PredictionExplanation)
class PredictionExplanationAdmin(admin.ModelAdmin):
    list_display = ('prediction', 'provider', 'model_identifier', 'created_at')
    list_filter = ('provider', 'model_identifier', 'created_at')
    search_fields = ('prediction__patient__patient_id', 'summary')
    readonly_fields = ('created_at', 'updated_at')


class DocumentChunkInline(admin.TabularInline):
    """
    Read-only view of what was actually indexed.

    Chunks are produced by the ingestion pipeline, never typed by hand, so
    editing them here would put the relational store and Chroma out of step.
    """

    model = DocumentChunk
    extra = 0
    can_delete = False
    readonly_fields = ('chunk_index', 'embedding_id', 'chunk_text', 'metadata')
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(KnowledgeDocument)
class KnowledgeDocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'source', 'document_type', 'active', 'chunk_count', 'ingested_at')
    list_filter = ('source', 'document_type', 'active')
    search_fields = ('title', 'citation')
    readonly_fields = ('ingested_at', 'chunk_count', 'content_hash', 'uploaded_at', 'updated_at')
    inlines = [DocumentChunkInline]

    fieldsets = (
        (None, {'fields': ('title', 'source', 'document_type', 'citation', 'file', 'active')}),
        ('Ingestion', {
            'fields': ('ingested_at', 'chunk_count', 'content_hash', 'uploaded_at', 'updated_at'),
            'description': (
                'Populated by <code>python manage.py ingest_sti_documents</code>. '
                'Uploading a file here does not index it; run the command afterwards.'
            ),
        }),
    )
