import { struct } from "./api.struct";


interface NoteType {
  id: NoteId;
  title: string;
  body: string;
  created_at: string;
}
export const Note = struct<NoteType>()("id", "title", "body", "created_at");
export type Note = NoteType;


interface NotesType {
  notes: Note[];
}
export const Notes = struct<NotesType>()("notes");
export type Notes = NotesType;


interface TestType {
  test: string;
}
export const Test = struct<TestType>()("test");
export type Test = TestType;


export type NoteId = number;


interface Notes2PostBodyType {
  note: Note;
  blank: number;
}
export const Notes2PostBody = struct<Notes2PostBodyType>()("note", "blank");
export type Notes2PostBody = Notes2PostBodyType;


interface NotesPostBodyType {
  note: Note;
  blank: number;
}
export const NotesPostBody = struct<NotesPostBodyType>()("note", "blank");
export type NotesPostBody = NotesPostBodyType;


interface NotesPostQueryType {
  dry_run: boolean;
}
export const NotesPostQuery = struct<NotesPostQueryType>()("dry_run");
export type NotesPostQuery = NotesPostQueryType;


type StaticEndpointSpec = {
  "notes.get": { response: Notes; body: never; query: never; path: never };
  "notes.list.get": { response: Test; body: never; query: never; path: never };
  "notes.post": { response: NotesPostBody; body: NotesPostBody; query: NotesPostQuery; path: never };
  "notes2.get": { response: Notes; body: never; query: never; path: never };
  "notes2.post": { response: Notes2PostBody; body: Notes2PostBody; query: never; path: never };
}


type DynamicEndpointCases = [
  { pattern: `notes.${string}.${string}.get`; response: Test; body: never; query: never; path: { id: string; page: string } },
  { pattern: `notes.${string}.get`; response: Test; body: never; query: never; path: { test: string } },
  { pattern: `test.${string}.get`; response: Test; body: never; query: never; path: { id: string } },
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
