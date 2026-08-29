"""
Build the RAG knowledge base from trusted STI guidance documents.

    python manage.py ingest_sti_documents
    python manage.py ingest_sti_documents --path docs/guidelines --source who
    python manage.py ingest_sti_documents --force
    python manage.py ingest_sti_documents --rebuild
    python manage.py ingest_sti_documents --status

Safe to run repeatedly: files whose contents have not changed are skipped,
and chunks are upserted under deterministic ids rather than appended.
"""

import os

from django.core.management.base import BaseCommand, CommandError

from ai_service.models import KnowledgeDocument
from ai_service.rag import ingestion, vector_store
from ai_service.rag.document_loader import SUPPORTED_EXTENSIONS
from ai_service.rag.errors import RagUnavailable


class Command(BaseCommand):
    help = 'Ingest trusted STI guidance documents into the RAG knowledge base.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--path',
            help=(
                'File or directory of documents to register and ingest. '
                'Without it, every active KnowledgeDocument already in the '
                'database is ingested.'
            ),
        )
        parser.add_argument(
            '--source',
            default='other',
            choices=[key for key, _ in KnowledgeDocument.SOURCES],
            help='Publishing authority for documents registered from --path.',
        )
        parser.add_argument(
            '--document-type',
            default='guideline',
            choices=[key for key, _ in KnowledgeDocument.DOCUMENT_TYPES],
            help='Document type for documents registered from --path.',
        )
        parser.add_argument(
            '--citation',
            default='',
            help='Citation label shown beside retrieved passages.',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Re-ingest even when the file is unchanged.',
        )
        parser.add_argument(
            '--rebuild',
            action='store_true',
            help='Drop the whole vector collection first, then ingest everything.',
        )
        parser.add_argument(
            '--status',
            action='store_true',
            help='Report what is currently indexed and exit.',
        )

    # -- helpers ------------------------------------------------------------

    def _check_dependencies(self):
        from ai_service.rag import embedding_service

        missing = []
        if not embedding_service.is_available():
            missing.append('sentence-transformers')
        if not vector_store.is_available():
            missing.append('chromadb')

        if missing:
            raise CommandError(
                'Missing required packages: {}\n'
                'Install them with:\n'
                '    pip install {}'.format(', '.join(missing), ' '.join(missing))
            )

    def _report_status(self):
        documents = KnowledgeDocument.objects.all()
        active = documents.filter(active=True).count()

        self.stdout.write(self.style.MIGRATE_HEADING('Knowledge base status'))
        self.stdout.write(f'  documents        : {documents.count()} ({active} active)')
        self.stdout.write(f'  vectors indexed  : {vector_store.count()}')
        self.stdout.write(f'  store path       : {vector_store.get_store_path()}')
        self.stdout.write(f'  collection       : {vector_store.get_collection_name()}')

        if not documents:
            self.stdout.write('')
            self.stdout.write(
                'No documents registered. Add some with:\n'
                '    python manage.py ingest_sti_documents --path <dir> --source who'
            )
            return

        self.stdout.write('')
        for document in documents:
            state = 'indexed' if document.is_indexed else 'not indexed'
            if not document.active:
                state = 'inactive'
            self.stdout.write(
                f'  [{state:>11}] {document.title} '
                f'({document.get_source_display()}, {document.chunk_count} chunks)'
            )

    def _register_path(self, path, options):
        """Create KnowledgeDocument rows for files not already registered."""
        if not os.path.exists(path):
            raise CommandError(f'Path not found: {path}')

        if os.path.isfile(path):
            candidates = [path]
        else:
            candidates = sorted(
                os.path.join(path, name)
                for name in os.listdir(path)
                if os.path.splitext(name)[1].lower() in SUPPORTED_EXTENSIONS
            )

        if not candidates:
            raise CommandError(
                f'No supported documents in {path}. '
                f'Supported: {", ".join(SUPPORTED_EXTENSIONS)}'
            )

        registered = []
        for candidate in candidates:
            name = os.path.basename(candidate)
            # Match on the stored filename so re-running with the same
            # directory does not create duplicate documents.
            if KnowledgeDocument.objects.filter(file__endswith=name).exists():
                self.stdout.write(f'  already registered: {name}')
                continue

            document = ingestion.register_file(
                candidate,
                source=options['source'],
                document_type=options['document_type'],
                citation=options['citation'],
            )
            registered.append(document)
            self.stdout.write(self.style.SUCCESS(f'  registered: {document.title}'))

        return registered

    # -- entry point --------------------------------------------------------

    def handle(self, *args, **options):
        if options['status']:
            self._report_status()
            return

        self._check_dependencies()

        if options['rebuild']:
            self.stdout.write('Dropping the existing collection...')
            try:
                vector_store.reset()
            except RagUnavailable as error:
                raise CommandError(str(error)) from error
            KnowledgeDocument.objects.update(chunk_count=0, ingested_at=None, content_hash='')

        if options['path']:
            self.stdout.write(self.style.MIGRATE_HEADING('Registering documents'))
            self._register_path(options['path'], options)

        if not KnowledgeDocument.objects.filter(active=True).exists():
            raise CommandError(
                'No active documents to ingest. Register some with --path, '
                'or upload them in the Django admin.'
            )

        self.stdout.write(self.style.MIGRATE_HEADING('Ingesting'))
        results = ingestion.ingest_all(force=options['force'] or options['rebuild'])

        ingested = skipped = failed = 0
        for result in results:
            if result.errors:
                failed += 1
                for message in result.errors:
                    self.stdout.write(self.style.ERROR(f'  FAILED  {result.title}: {message}'))
            elif result.skipped:
                skipped += 1
                self.stdout.write(f'  skipped {result.title} ({result.reason})')
            else:
                ingested += 1
                self.stdout.write(self.style.SUCCESS(
                    f'  ok      {result.title} -> {result.chunks_created} chunks'
                ))

        self.stdout.write('')
        self.stdout.write(
            f'{ingested} ingested, {skipped} skipped, {failed} failed. '
            f'{vector_store.count()} vectors in the store.'
        )

        # Non-zero exit so CI notices a partial failure.
        if failed:
            raise CommandError(f'{failed} document(s) failed to ingest.')
