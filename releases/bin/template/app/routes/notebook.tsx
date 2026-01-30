import { useEffect, useState } from "react";
import { api } from "tsunami";

export default function() {
  const [body, setBody] = useState<string>("")

  useEffect(async () => {
    let mounted = true
    
    try {
        const note = await api("note.234.get")
        
        if (mounted) setBody(note?.[0]?.body ?? "");
    } catch(err) {
        console.error("Failed to load note", err)
    }

    return () => {
      mounted = false
    }
  }, [])

  return <p>Notebooks: {body}</p>;
}
