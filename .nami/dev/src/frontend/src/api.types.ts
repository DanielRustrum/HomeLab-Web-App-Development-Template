import { struct } from "./api.struct";


interface NoteObject {
  title: Unique<string>;
  body: string;
  test: string;
  created_at: string;
  id: Key<NoteId>;
}
export const Note = struct<NoteObject>()("title", "body", "test", "created_at", "id");
export type Note = NoteObject;


interface NoteInsertObject {
  title: Unique<string>;
  body: string;
  test: string;
  created_at: string;
}
export const NoteInsert = struct<NoteInsertObject>()("title", "body", "test", "created_at");
export type NoteInsert = NoteInsertObject;


interface NotesObject {
  notes: Note[];
}
export const Notes = struct<NotesObject>()("notes");
export type Notes = NotesObject;


interface TestObject {
  test: string;
}
export const Test = struct<TestObject>()("test");
export type Test = TestObject;


export type NoteId = string;


interface NotebookTitlePostBodyObject {
  note: Note;
}
export const NotebookTitlePostBody = struct<NotebookTitlePostBodyObject>()("note");
export type NotebookTitlePostBody = NotebookTitlePostBodyObject;


interface Notes2PostBodyObject {
  note: Note;
  blank: number;
}
export const Notes2PostBody = struct<Notes2PostBodyObject>()("note", "blank");
export type Notes2PostBody = Notes2PostBodyObject;


interface NotesPostBodyObject {
  note: NoteInsert;
}
export const NotesPostBody = struct<NotesPostBodyObject>()("note");
export type NotesPostBody = NotesPostBodyObject;


interface TestPostBodyObject {
  blank: string;
}
export const TestPostBody = struct<TestPostBodyObject>()("blank");
export type TestPostBody = TestPostBodyObject;


interface Notes2PostQueryObject {
  dry_run: boolean;
}
export const Notes2PostQuery = struct<Notes2PostQueryObject>()("dry_run");
export type Notes2PostQuery = Notes2PostQueryObject;


export type Key<T> = T;
export type Unique<T> = T;


type StaticEndpointSpec = {
  "notes.get": { response: Notes; body: never; query: never; path: never };
  "notes.list.get": { response: Test; body: never; query: never; path: never };
  "notes.post": { response: NotesPostBody; body: NotesPostBody; query: never; path: never };
  "notes2.get": { response: Notes; body: never; query: never; path: never };
  "notes2.post": { response: Notes2PostBody; body: Notes2PostBody; query: Notes2PostQuery; path: never };
}


type DynamicEndpointCases = [
  { pattern: `notes.${string}.${string}.get`; response: Test; body: never; query: never; path: { id: string; page: string } },
  { pattern: `notebook.${string}.post`; response: NotebookTitlePostBody; body: NotebookTitlePostBody; query: never; path: { title: string } },
  { pattern: `notebook.${string}.get`; response: Notes; body: never; query: never; path: { title: string } },
  { pattern: `notes.${string}.get`; response: Test; body: never; query: never; path: { test: string } },
  { pattern: `test.${string}.get`; response: Test; body: never; query: never; path: { id: string } },
  { pattern: `${string}.post`; response: TestPostBody; body: TestPostBody; query: never; path: { test: string } },
  { pattern: `${string}.get`; response: Test; body: never; query: never; path: { test: string } },
]


type DefaultEndpointSpec = { response: unknown; body: never; query: never; path: never };

type MatchDynamicSpec<Key extends string, Cases extends readonly unknown[]> =
  Cases extends readonly [infer Head, ...infer Tail extends readonly unknown[]]
    ? Head extends { pattern: infer Pattern }
      ? Pattern extends string
        ? Key extends Pattern
          ? Head
          : MatchDynamicSpec<Key, Tail>
        : DefaultEndpointSpec
      : DefaultEndpointSpec
    : DefaultEndpointSpec;


export type EndpointKey = keyof StaticEndpointSpec | DynamicEndpointCases[number]['pattern'];

type EndpointSpecFor<Key extends EndpointKey> =
  Key extends keyof StaticEndpointSpec
    ? StaticEndpointSpec[Key]
    : MatchDynamicSpec<Key, DynamicEndpointCases>;


export type Endpoints = { [Key in EndpointKey]: EndpointSpecFor<Key>['response'] };
export type EndpointParams = { [Key in EndpointKey]: EndpointSpecFor<Key>['body'] };
export type EndpointQueryParams = { [Key in EndpointKey]: EndpointSpecFor<Key>['query'] };
export type EndpointPathParams = { [Key in EndpointKey]: EndpointSpecFor<Key>['path'] };


export type EndpointSpec<K extends EndpointKey> = EndpointSpecFor<K>;
export type EndpointResponse<K extends EndpointKey> = EndpointSpecFor<K>["response"];
export type EndpointBody<K extends EndpointKey> = EndpointSpecFor<K>["body"];
export type EndpointQuery<K extends EndpointKey> = EndpointSpecFor<K>["query"];
export type EndpointPath<K extends EndpointKey> = EndpointSpecFor<K>["path"];
