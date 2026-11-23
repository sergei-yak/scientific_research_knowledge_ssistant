# Presentation speech - v5

Sergei Iakovlev | DBU Deep Learning | 22 November 2026

Twelve slides for the professor's final-project showcase. The opening research team is hypothetical. The course reflection draft was explicitly accepted by Sergei. Scientific results remain unchanged.

**Timing:** 1,092 spoken words, approximately 9.1 minutes at 120 words/minute. Allow another 2-3 minutes for the slide-5 demo and about one minute for pauses/transitions. Target roughly 12-13 minutes within the required 10-15. This is an estimate, not a measured rehearsal. Speaker-note citations are not spoken.

## Slide 1 - Scientific Research Knowledge Assistant

Imagine a research team trying to choose a new method. The evidence is spread across papers, and checking one answer means opening several documents. My project starts with that everyday problem. I built a local assistant that accepts research papers, answers questions, and lets the user inspect the original sources. Today I will show the working product, explain the challenges behind it, and share what the tests taught me about adding graph connections.

## Slide 2 - The research team's problem

Picture a researcher with ten papers open. One describes a method, another uses the same dataset, and a third explains a limitation. A quick answer is useful only if the researcher can check where it came from. My intended users are students and research teams making sense of a collection of papers. The business idea is to reduce repeated searching and make evidence easier to inspect. I have demonstrated the workflow, but I have not measured time savings or financial return. That would require a separate study with real users.

## Slide 3 - Graph RAG: entities and relationships

Imagine two papers. One says Method A was tested on Dataset X. The other says the same about Method B. Traditional RAG finds useful passages for an AI to read. Graph RAG also organizes information into a map. Important things, called entities, become nodes. Here they are Method A, Method B and Dataset X. Relationships become labelled edges. Each evaluated-on arrow connects a method to its dataset. We can follow those links to find methods tested on Dataset X, then retrieve the original passages. My project requires human review of proposed connections. The research question is whether this extra structure gives the answer writer more useful evidence. This example illustrates the idea, rather than a measured result.

## Slide 4 - How the application works

The application follows a simple sequence. First, it reads a paper and saves searchable passages with their source locations. When someone asks a question, search selects a small reading pack. The local AI can then write an answer from that evidence. Finally, the user can open the sources and export the result. Optional reviewed claims support fact and graph search. I also tested an extra relevance checker in the research study. It is an experimental option, rather than a required stage in the demonstrated product. I used pretrained models and did not train a new neural network.

## Slide 5 - Your papers, your research questions

Let us follow the researcher's journey in the app. I will show the paper-import controls, select an existing collection, ask a question, and open the supporting passage. Using a prepared collection keeps the demonstration short. The screenshot shows a previously generated answer about gravitational waves. Live evidence search works without generating another answer. I can also export the evidence. Ordinary search becomes available after indexing. Fact and graph modes need that collection's own reviewed claims. New collections stay separate from the research experiments. I will now switch to the application for a short walkthrough.

## Slide 6 - Challenges and implemented solutions

The first challenge was trust in the input. PDF reading order and generated claims can be imperfect. I kept exact quotations and page references, and required a person to review claims before publication. The second challenge was limited local hardware. I limited the reading pack and output length, and ran one inference at a time. The third was keeping collections and reviews consistent. Document hashes, collection revisions and current-review checks help prevent stale evidence from appearing. These choices made the workflow more controlled. They did not eliminate extraction errors, slow answers, or the need for human judgment.

## Slide 7 - How I tested the idea

A good-looking demonstration does not tell us which search approach gives better answers. I built a checked research library of twenty papers and compared four approaches: meaning search, meaning plus words, reviewed claims, and graph connections. They received the same questions and evidence limits within each study. I rated anonymous answers before revealing which approach produced them. There were two small studies, each with sixteen held-out questions. I was the only scorer. The follow-up question author had seen earlier outcomes, so that study is exploratory. The two studies used different held-out questions, which prevents a direct improvement claim between them.

## Slide 8 - What the tests showed

In the first study, combining meaning search with matching words gave the highest average reviewer score. The chart uses ratings from zero to one, not percentages of correct answers. Graph search tied the version using reviewed claims. No additional graph evidence entered the final reading pack for any held-out question. The follow-up tested broader connections and an extra relevance checker. That checker helped some approaches, hurt another, and added retrieval time. Graph again supplied no new selected evidence on the held-out questions. My conclusion is specific: this implementation did not demonstrate a graph benefit under these conditions. It does not establish that Graph RAG can never help.

## Slide 9 - Current limitations

The limits matter when deciding where to use this product. The studies were small and used one reviewer. The follow-up also has the question-author exposure I mentioned. Paper coverage and reviewed connections are incomplete, and a citation does not guarantee every sentence is correct. The app is a local, single-user release. It supports text-based PDFs, rather than every website or scanned document. Local answer generation can take tens of seconds. A useful next business test would observe whether real researchers can complete their work more easily and check answers successfully.

## Slide 10 - Future enhancements

The next improvements should address the gaps we actually observed. First, build more useful reviewed connections while preserving their original sources. Second, evaluate a revised system on fresh questions with cleanly separated authors and independent reviewers. Third, test the product with real users, then investigate larger collections and scanned papers if those users need them. Uploads and separate research collections already work. These are proposals for future work, rather than features I have completed or evidence that answer quality will improve.

## Slide 11 - Course reflection

This project helped me think beyond getting an AI model to return an answer. I had to consider the data, the source of each statement, the user experience, and how to test the result. The biggest lesson was to check whether an added component earns its complexity. The graph result was negative, but reporting that honestly was part of the learning. My next interest is building reliable AI applications that people can question and verify. I would carry the same source checks and fair comparisons into future coding projects.

## Slide 12 - References and project resources

These are the main research and software resources behind the project. The full citations and model details are in the notes and companion reference file. The repository contains the implementation, documentation and public results. Private evaluation material and local model assets are excluded. Thank you. I am happy to show a source or discuss a design choice.

After slide 5, perform the short walkthrough in Demo_Rehearsal.md. If using recorded material, identify it as recorded. Personalize the accepted reflection if it does not match your experience.
