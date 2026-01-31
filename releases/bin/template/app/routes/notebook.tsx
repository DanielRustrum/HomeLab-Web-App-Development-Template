import { useEffect, useState } from "react";
import { api } from "tsunami";

export default function() {
  const [body, setBody] = useState<string>("")

  useEffect(async () => {
    let mounted = true
    
    try {
        const note = await api("note.234.get")
        
        console.log(note)
        if (mounted) setBody(note.notes[0].body ?? "");
    } catch(err) {
        console.error("Failed to load note", err)
    }

    return () => {
      mounted = false
    }
  }, [])

  return (
    <div>
      <p>Notebooks: {body}</p>
      <button
        onClick={async () => {
          await api("note.234.post", {
            title: "New Note",
            body: "body???",
            test: "",
            created_at: new Date().toISOString(),
          });
        }}
      >
        Add Note
      </button>
    </div>
  );
}
