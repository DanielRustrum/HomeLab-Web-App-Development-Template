from dataclasses import dataclass
from uuid import UUID, uuid4

from tsunami import db

type NoteId = UUID
type Result[T] = T
type Pair[T, U] = tuple[T, U]


@dataclass
class NoteInsert:
    title: db.Unique[str]
    body: str
    test: str
    created_at: str

@db.table
@dataclass
class Note(NoteInsert):
    id: db.Key[NoteId]

@db.table
@dataclass
class Notebook:
    id: db.Key[UUID]
    book_title: db.Unique[str]
    note_id: NoteId

@dataclass
class Notes:
    notes: list[Note]

@dataclass
class NotebookTitles:
    book_titles: list[str]



#* ==== Queries ===

class Queries: 
    @db.query
    def get_notes() -> Notes:
        with db.Table(Note) as notes:
            return Notes(notes.fetch_all())

    @db.query
    def get_5_notes() -> Notes:
        with db.Table(Note) as notes:
            return Notes(notes.fetch_amount(5))

    @db.query
    def add_note(note: NoteInsert) -> None:
        with db.Table(Note) as notes:
            notes.insert(Note(
                uuid4(),
                note.title,
                note.body,
                note.test,
                note.created_at,
            ))

    @db.query
    def remove_note(title: str) -> None:
        with db.Table(Note) as notes:
            notes.where(notes.title == title).delete()

    @db.query
    def update_notebook(book_title: str, note: Note) -> None:
        with db.Table(Notebook) as notebook:
            notebook.insert(UUID(), book_title, note.id)

    @db.query
    def get_notebook_notes(book_title: str) -> Notes:
        with db.Table([Notebook, Note]) as (notebook, notes):
            return Notes(
                notes
                .join(notebook, when=(notes.id == notebook.note_id))
                .where(notebook.book_title == book_title)
                .fetch_all()
            )

    @db.query
    def get_notebooks() -> NotebookTitles:
        with db.Table(Notebook) as notebook:
            return NotebookTitles(notebook.select("book_title").fetch_all())

    @db.query
    def get_notebook_page_count(book_title: str) -> int:
        with db.Table(Notebook) as notebook:
            return notebook.where(notebook.book_title == book_title).count()

    @db.query
    def check_for_note(title: str) -> bool:
        with db.Table(Note) as notes:
            return notes.where(notes.title == title).exists()

    @db.query
    def rename_note(title: str, new_title: str) -> None:
        with db.Table(Note) as notes:
            notes.where(notes.title == title).update(title=new_title)

    @db.query
    def search_notebook(query: str) -> Notes:
        with db.Table(Note) as notes:
            return Notes(notes.pattern(query, on=[notes.title]).fetch_all())
