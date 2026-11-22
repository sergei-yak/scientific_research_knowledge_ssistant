# Presentation speech

Sergei Iakovlev | DBU Deep Learning | 21 November 2026

Eleven slides, with an early RAG comparison and a simple research-team story. The opening team is hypothetical. M8 is the completed product extension; scientific results remain unchanged. Rehearsal duration is an estimate until Sergei measures his own delivery.

## Slide 1 - Scientific Research Knowledge Assistant

Imagine you are part of a research team. Your manager asks, "Which method should we try, and what evidence supports that choice?"

You have papers open everywhere. One explains a method, another lists its weaknesses, and a third uses a different test. Checking an answer means moving between documents.

That is the problem behind my project. I built an assistant that lets people bring their own research papers, ask questions, and inspect the original sources behind an answer. The business idea is easier research and easier checking. I tested the system and answer quality, but I have not measured business time savings.

## Slide 2 - Traditional RAG and Graph RAG: what changes?

Before we look inside the project, imagine these papers as a small library. RAG means the assistant looks up source material before writing an answer.

Traditional RAG finds passages related to your question. It can bring together passages from several documents. Graph RAG adds a map of connections, such as which methods use a particular test dataset.

Suppose we ask, "Which methods use the same test data?" Traditional RAG searches for relevant text. Graph RAG can also follow the stored links between methods and that dataset, then bring back the supporting text.

My question was whether those extra connections would help people get better answers. They might help, but we need to test that.

## Slide 3 - Is following connections worth the extra work?

Now our researcher has two possible ways to search the library. To find out whether connections help, I needed a fair comparison.

I tested four approaches. The first searches by meaning. The second combines meaning with matching words. The third also searches claims that a person has checked against the papers. The fourth can follow connections between those reviewed claims and their related research.

Each approach gets the same limit on how much evidence it can give the answer writer. That matters because a larger reading pack could improve an answer by itself.

If the connection search adds nothing useful to the final pack, the system says so and uses the matching simpler result.

## Slide 4 - Three roles: find, check and write

Think of the assistant as having three roles. One finds material that might answer the question. Another gives the possible passages a closer relevance check. The last writes an answer from the selected evidence.

The names and numbers on this slide describe the AI tools doing those jobs. I compared two search models and later tested the extra checking step. For the answer writer, I used a model running on my own computer.

I used models that were already trained. I did not train a new neural network. My work was building the system around them and testing whether the way I found and selected evidence made the answers more useful.

## Slide 5 - Building a small library we can check

Before opening the app to different topics, I needed a small library that I could check carefully. I started with five AI papers, then expanded to twenty.

Those research experiments used 1,427 searchable passages and 51 claims reviewed against their sources. Each reviewed statement keeps its original wording and page reference.

That matters for our researcher. If an answer describes a limitation, they can open the passage and check it. Approval means the paper supports the statement; it does not mean I repeated the scientific experiment.

The product can now accept new collections. Those stay separate from this research library, so adding a new paper does not change the results I am about to show.

## Slide 6 - Testing the idea fairly

At this point, the assistant could answer questions. But a convincing demonstration alone would not tell me which search approach worked better.

I prepared two studies. Within each study, every approach received the same questions. Some asked for a simple fact, some needed several papers, and some had no supported answer in the collection.

I scored the answers without seeing which approach had produced each one. The scale allowed wrong, partly correct, and fully supported answers. I was the only scorer, so this is a small study.

The follow-up also has a limitation: its question author had seen earlier outcomes. I treat it as exploratory. Its different questions prevent a direct improvement claim between the two studies.

## Slide 7 - First study: combined search worked best here

The first study gave me a useful surprise. Combining search by meaning with matching words produced the highest average answer score in the test sample. You can see that in the taller Hybrid bar.

These are reviewer scores on a scale from zero to one, not percentages of correct answers.

The graph approach did not improve on the version with reviewed claims. For every held-out question, no extra graph evidence entered the final answer material. It used the same evidence as that simpler version.

For our research team, that matters. A more complicated system needs to earn its place. In this test, I had no evidence that following connections added answer value.

## Slide 8 - Second study: a closer look helped some searches

After that result, I investigated two changes. Could a broader search through the connections help? And could an extra relevance check choose better material for the answer writer?

Think of that second change as reading the shortlist more carefully before handing it over.

In the follow-up sample, broader connections alone did not improve the answer scores. The extra checking step helped some search approaches, but it hurt another and took more retrieval time. It was not a universal improvement.

The business lesson is to test each added step against the work it is meant to support. An extra AI component should show a useful benefit, rather than simply make the system more elaborate.

## Slide 9 - Did the connections improve the answers?

This slide returns to the main question. Did graph connections improve answers beyond what the reviewed claims already provided?

In the main follow-up comparison, all sixteen held-out questions were ties. The graph stage added retrieval time, but no new graph evidence reached the answer writer.

That does not show that Graph RAG can never help. My collection was small, and the reviewed connections may not have supplied the missing evidence these questions needed. It shows that this implementation did not demonstrate that benefit here.

For a team choosing a tool, I would present that result honestly. I would need stronger evidence before recommending the extra graph work for better answers.

## Slide 10 - Your papers, your research questions

Now imagine our researcher changes jobs or starts a different topic. They should not be limited to the papers I selected for class.

In the app, they create a collection, upload PDFs or paste public paper links, and wait for the papers to become searchable. Then they ask a question. They can inspect passages alone, or ask the local AI to write an answer.

This screenshot shows a real physics-paper example about gravitational waves. I also checked the app on AI papers. The source cards let the user open the original page and export the evidence.

Ordinary search works immediately after indexing. Graph search needs claims and connections that a person has reviewed. If it adds no useful evidence, the app says so. These product checks show the workflow works; they are not a new accuracy study.

## Slide 11 - What this could mean for a research team

We started with a team trying to understand information scattered across papers. The working product now lets that team bring its own documents and follow an answer back to its sources.

The intended business value is less repeated searching and an easier way to check a recommendation. Those benefits still need testing with real users; I have not measured financial return or time savings.

The research also changed what I would recommend. Graph connections did not improve the held-out answers here. Some ranking changes helped, with trade-offs.

My future research would examine more useful reviewed connections and a fresh evaluation. Today, I can demonstrate a local research assistant and explain clearly what the evidence supports. I used pretrained models; I did not train a new neural network.
