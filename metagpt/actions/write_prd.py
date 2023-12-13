#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2023/5/11 17:45
@Author  : alexanderwu
@File    : write_prd.py
@Modified By: mashenquan, 2023/11/27.
            1. According to Section 2.2.3.1 of RFC 135, replace file data in the message with the file name.
            2. According to the design in Section 2.2.3.5.2 of RFC 135, add incremental iteration functionality.
            3. Move the document storage operations related to WritePRD from the save operation of WriteDesign.
@Modified By: mashenquan, 2023/12/5. Move the generation logic of the project name to WritePRD.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List

from metagpt.actions import Action, ActionOutput
from metagpt.actions.fix_bug import FixBug
from metagpt.actions.search_and_summarize import SearchAndSummarize
from metagpt.config import CONFIG
from metagpt.const import (
    COMPETITIVE_ANALYSIS_FILE_REPO,
    DOCS_FILE_REPO,
    PRD_PDF_FILE_REPO,
    PRDS_FILE_REPO,
    REQUIREMENT_FILENAME, BUGFIX_FILENAME,
)
from metagpt.logs import logger
from metagpt.schema import Document, Documents, Message, BugFixContext
from metagpt.utils.common import CodeParser
from metagpt.utils.file_repository import FileRepository
from metagpt.utils.get_template import get_template
from metagpt.utils.mermaid import mermaid_to_file

templates = {
    "json": {
        "PROMPT_TEMPLATE": """
# Context
{{
    "Original Requirements": "{requirements}",
    "Search Information": ""
}} 

## Format example
{format_example}
-----
Role: You are a professional product manager; the goal is to design a concise, usable, efficient product
Language: Please use the same language as the user requirement, but the title and code should be still in English. For example, if the user speaks Chinese, the specific text of your answer should also be in Chinese.
Requirements: According to the context, fill in the following missing information, note that each sections are returned in Python code triple quote form seperatedly.
ATTENTION: Output carefully referenced "Format example" in format.

## YOU NEED TO FULFILL THE BELOW JSON DOC

{{
    "Language": "", # str, use the same language as the user requirement. en_us / zh_cn etc.
    "Original Requirements": "", # str, place the polished complete original requirements here
    "Project Name": "{project_name}", # str, if it's empty, name it with snake case style, like game_2048 / web_2048 / simple_crm etc.
    "Search Information": "",
    "Requirements": "", 
    "Product Goals": [], # Provided as Python list[str], up to 3 clear, orthogonal product goals.
    "User Stories": [], # Provided as Python list[str], up to 5 scenario-based user stories
    "Competitive Analysis": [], # Provided as Python list[str], up to 8 competitive product analyses
    # Use mermaid quadrantChart code syntax. up to 14 competitive products. Translation: Distribute these competitor scores evenly between 0 and 1, trying to conform to a normal distribution centered around 0.5 as much as possible.
    "Competitive Quadrant Chart": "quadrantChart
                title Reach and engagement of campaigns
                x-axis Low Reach --> High Reach
                y-axis Low Engagement --> High Engagement
                quadrant-1 We should expand
                quadrant-2 Need to promote
                quadrant-3 Re-evaluate
                quadrant-4 May be improved
                Campaign A: [0.3, 0.6]
                Campaign B: [0.45, 0.23]
                Campaign C: [0.57, 0.69]
                Campaign D: [0.78, 0.34]
                Campaign E: [0.40, 0.34]
                Campaign F: [0.35, 0.78]",
    "Requirement Analysis": "", # Provide as Plain text.
    "Requirement Pool": [["P0","P0 requirement"],["P1","P1 requirement"]], # Provided as Python list[list[str], the parameters are requirement description, priority(P0/P1/P2), respectively, comply with PEP standards
    "UI Design draft": "", # Provide as Plain text. Be simple. Describe the elements and functions, also provide a simple style description and layout description.
    "Anything UNCLEAR": "", # Provide as Plain text. Try to clarify it.
}}

output a properly formatted JSON, wrapped inside [CONTENT][/CONTENT] like format example,
and only output the json inside this tag, nothing else
""",
        "FORMAT_EXAMPLE": """
[CONTENT]
{{
    "Language": "",
    "Original Requirements": "",
    "Project Name": "{project_name}",
    "Search Information": "",
    "Requirements": "",
    "Product Goals": [],
    "User Stories": [],
    "Competitive Analysis": [],
    "Competitive Quadrant Chart": "quadrantChart
                title Reach and engagement of campaigns
                x-axis Low Reach --> High Reach
                y-axis Low Engagement --> High Engagement
                quadrant-1 We should expand
                quadrant-2 Need to promote
                quadrant-3 Re-evaluate
                quadrant-4 May be improved
                Campaign A: [0.3, 0.6]
                Campaign B: [0.45, 0.23]
                Campaign C: [0.57, 0.69]
                Campaign D: [0.78, 0.34]
                Campaign E: [0.40, 0.34]
                Campaign F: [0.35, 0.78]",
    "Requirement Analysis": "",
    "Requirement Pool": [["P0","P0 requirement"],["P1","P1 requirement"]],
    "UI Design draft": "",
    "Anything UNCLEAR": "",
}}
[/CONTENT]
""",
    },
    "markdown": {
        "PROMPT_TEMPLATE": """
# Context
## Original Requirements
{requirements}

## Search Information
{search_information}

## mermaid quadrantChart code syntax example. DONT USE QUOTO IN CODE DUE TO INVALID SYNTAX. Replace the <Campain X> with REAL COMPETITOR NAME
```mermaid
quadrantChart
    title Reach and engagement of campaigns
    x-axis Low Reach --> High Reach
    y-axis Low Engagement --> High Engagement
    quadrant-1 We should expand
    quadrant-2 Need to promote
    quadrant-3 Re-evaluate
    quadrant-4 May be improved
    "Campaign: A": [0.3, 0.6]
    "Campaign B": [0.45, 0.23]
    "Campaign C": [0.57, 0.69]
    "Campaign D": [0.78, 0.34]
    "Campaign E": [0.40, 0.34]
    "Campaign F": [0.35, 0.78]
    "Our Target Product": [0.5, 0.6]
```

## Format example
{format_example}
-----
Role: You are a professional product manager; the goal is to design a concise, usable, efficient product
Language: Please use the same language as the user requirement to answer, but the title and code should be still in English. For example, if the user speaks Chinese, the specific text of your answer should also be in Chinese.
Requirements: According to the context, fill in the following missing information, note that each sections are returned in Python code triple quote form seperatedly.
ATTENTION: Use '##' to SPLIT SECTIONS, not '#'. AND '## <SECTION_NAME>' SHOULD WRITE BEFORE the code and triple quote. Output carefully referenced "Format example" in format.

## Language: Provide as Plain text, use the same language as the user requirement.

## Original Requirements: Provide as Plain text, place the polished complete original requirements here

## Product Goals: Provided as Python list[str], up to 3 clear, orthogonal product goals.

## User Stories: Provided as Python list[str], up to 5 scenario-based user stories

## Competitive Analysis: Provided as Python list[str], up to 7 competitive product analyses, consider as similar competitors as possible

## Competitive Quadrant Chart: Use mermaid quadrantChart code syntax. up to 14 competitive products. Translation: Distribute these competitor scores evenly between 0 and 1, trying to conform to a normal distribution centered around 0.5 as much as possible.

## Requirement Analysis: Provide as Plain text.

## Requirement Pool: Provided as Python list[list[str], the parameters are requirement description, priority(P0/P1/P2), respectively, comply with PEP standards

## UI Design draft: Provide as Plain text. Be simple. Describe the elements and functions, also provide a simple style description and layout description.
## Anything UNCLEAR: Provide as Plain text. Try to clarify it.
""",
        "FORMAT_EXAMPLE": """
---
## Original Requirements
The user ... 

## Product Goals
```python
[
    "Create a ...",
]
```

## User Stories
```python
[
    "As a user, ...",
]
```

## Competitive Analysis
```python
[
    "Python Snake Game: ...",
]
```

## Competitive Quadrant Chart
```mermaid
quadrantChart
    title Reach and engagement of campaigns
    ...
    "Our Target Product": [0.6, 0.7]
```

## Requirement Analysis
The product should be a ...

## Requirement Pool
```python
[
    ["End game ...", "P0"]
]
```

## UI Design draft
Give a basic function description, and a draft

## Anything UNCLEAR
There are no unclear points.
---
""",
    },
}

OUTPUT_MAPPING = {
    "Language": (str, ...),
    "Original Requirements": (str, ...),
    "Project Name": (str, ...),
    "Product Goals": (List[str], ...),
    "User Stories": (List[str], ...),
    "Competitive Analysis": (List[str], ...),
    "Competitive Quadrant Chart": (str, ...),
    "Requirement Analysis": (str, ...),
    "Requirement Pool": (List[List[str]], ...),
    "UI Design draft": (str, ...),
    "Anything UNCLEAR": (str, ...),
}

IS_RELATIVE_PROMPT = """
## PRD:
{old_prd}

## New Requirement:
{requirements}

___
You are a professional product manager; You need to assess whether the new requirements are relevant to the existing PRD to determine whether to merge the new requirements into this PRD.
Is the newly added requirement in "New Requirement" related to the PRD? 
Respond with `YES` if it is related, `NO` if it is not, and provide the reasons. Return the response in JSON format.
"""

MERGE_PROMPT = """
# Context
## Original Requirements
{requirements}


## Old PRD
{old_prd}
-----
Role: You are a professional product manager; The goal is to incorporate the newly added requirements from the "Original Requirements" into the existing Product Requirements Document (PRD) in the "Old PRD" in order to design a concise, usable, and efficient product.
Language: Please use the same language as the user requirement, but the title and code should be still in English. For example, if the user speaks Chinese, the specific text of your answer should also be in Chinese.
Requirements: According to the context, fill in the following missing information, each section name is a key in json ,If the requirements are unclear, ensure minimum viability and avoid excessive design
ATTENTION: Output carefully referenced "Old PRD" in format.

## YOU NEED TO FULFILL THE BELOW JSON DOC

{{
    "Language": "", # str, use the same language as the user requirement. en_us / zh_cn etc.
    "Original Requirements": "", # str, place the polished complete original requirements here
    "Project Name": "{project_name}", # str, if it's empty, name it with snake case style, like game_2048 / web_2048 / simple_crm etc.
    "Search Information": "",
    "Requirements": "", 
    "Product Goals": [], # Provided as Python list[str], up to 3 clear, orthogonal product goals.
    "User Stories": [], # Provided as Python list[str], up to 5 scenario-based user stories
    "Competitive Analysis": [], # Provided as Python list[str], up to 8 competitive product analyses
    # Use mermaid quadrantChart code syntax. up to 14 competitive products. Translation: Distribute these competitor scores evenly between 0 and 1, trying to conform to a normal distribution centered around 0.5 as much as possible.
    "Competitive Quadrant Chart": "quadrantChart
                title Reach and engagement of campaigns
                x-axis Low Reach --> High Reach
                y-axis Low Engagement --> High Engagement
                quadrant-1 We should expand
                quadrant-2 Need to promote
                quadrant-3 Re-evaluate
                quadrant-4 May be improved
                Campaign A: [0.3, 0.6]
                Campaign B: [0.45, 0.23]
                Campaign C: [0.57, 0.69]
                Campaign D: [0.78, 0.34]
                Campaign E: [0.40, 0.34]
                Campaign F: [0.35, 0.78]",
    "Requirement Analysis": "", # Provide as Plain text.
    "Requirement Pool": [["P0","P0 requirement"],["P1","P1 requirement"]], # Provided as Python list[list[str], the parameters are requirement description, priority(P0/P1/P2), respectively, comply with PEP standards
    "UI Design draft": "", # Provide as Plain text. Be simple. Describe the elements and functions, also provide a simple style description and layout description.
    "Anything UNCLEAR": "", # Provide as Plain text. Try to clarify it.
}}

output a properly formatted JSON, wrapped inside [CONTENT][/CONTENT] like "Old PRD" format,
and only output the json inside this tag, nothing else
"""

IS_BUGFIX_PROMPT = """
{content}

___
You are a professional product manager; You need to determine whether the above content describes a requirement or provides feedback about a bug.
Respond with `YES` if it is a feedback about a bug, `NO` if it is not, and provide the reasons. Return the response in JSON format like below:

```json
{{
    "is_bugfix": ..., # `YES` or `NO`
    "reason": ..., # reason string
}}
```
"""


class WritePRD(Action):
    def __init__(self, name="", context=None, llm=None):
        super().__init__(name, context, llm)

    async def run(self, with_messages, format=CONFIG.prompt_format, *args, **kwargs) -> ActionOutput | Message:
        # Determine which requirement documents need to be rewritten: Use LLM to assess whether new requirements are
        # related to the PRD. If they are related, rewrite the PRD.
        docs_file_repo = CONFIG.git_repo.new_file_repository(relative_path=DOCS_FILE_REPO)
        requirement_doc = await docs_file_repo.get(filename=REQUIREMENT_FILENAME)
        if await self._is_bugfix(requirement_doc.content):
            await docs_file_repo.save(filename=BUGFIX_FILENAME, content=requirement_doc.content)
            await docs_file_repo.save(filename=REQUIREMENT_FILENAME, content="")
            bug_fix = BugFixContext(filename=BUGFIX_FILENAME)
            return Message(content=bug_fix.json(), instruct_content=bug_fix,
                           role=self.profile,
                           cause_by=FixBug,
                           sent_from=self,
                           send_to="Alex",  # the name of Engineer
                           )
        else:
            await docs_file_repo.delete(filename=BUGFIX_FILENAME)

        prds_file_repo = CONFIG.git_repo.new_file_repository(PRDS_FILE_REPO)
        prd_docs = await prds_file_repo.get_all()
        change_files = Documents()
        for prd_doc in prd_docs:
            prd_doc = await self._update_prd(
                requirement_doc=requirement_doc, prd_doc=prd_doc, prds_file_repo=prds_file_repo, *args, **kwargs
            )
            if not prd_doc:
                continue
            change_files.docs[prd_doc.filename] = prd_doc
            logger.info(f"REWRITE PRD:{prd_doc.filename}")
        # If there is no existing PRD, generate one using 'docs/requirement.txt'.
        if not change_files.docs:
            prd_doc = await self._update_prd(
                requirement_doc=requirement_doc, prd_doc=None, prds_file_repo=prds_file_repo, *args, **kwargs
            )
            if prd_doc:
                change_files.docs[prd_doc.filename] = prd_doc
                logger.debug(f"new prd: {prd_doc.filename}")
        # Once all files under 'docs/prds/' have been compared with the newly added requirements, trigger the
        # 'publish' message to transition the workflow to the next stage. This design allows room for global
        # optimization in subsequent steps.
        return ActionOutput(content=change_files.json(), instruct_content=change_files)

    async def _run_new_requirement(self, requirements, format=CONFIG.prompt_format, *args, **kwargs) -> ActionOutput:
        sas = SearchAndSummarize()
        # rsp = await sas.run(context=requirements, system_text=SEARCH_AND_SUMMARIZE_SYSTEM_EN_US)
        rsp = ""
        info = f"### Search Results\n{sas.result}\n\n### Search Summary\n{rsp}"
        if sas.result:
            logger.info(sas.result)
            logger.info(rsp)

        # logger.info(format)
        prompt_template, format_example = get_template(templates, format)
        project_name = CONFIG.project_name if CONFIG.project_name else ""
        format_example = format_example.format(project_name=project_name)
        # logger.info(prompt_template)
        # logger.info(format_example)
        prompt = prompt_template.format(
            requirements=requirements, search_information=info, format_example=format_example, project_name=project_name
        )
        # logger.info(prompt)
        # prd = await self._aask_v1(prompt, "prd", OUTPUT_MAPPING)
        prd = await self._aask_v1(prompt, "prd", OUTPUT_MAPPING, format=format)
        await self._rename_workspace(prd)
        return prd

    async def _is_relative_to(self, new_requirement_doc, old_prd_doc) -> bool:
        prompt = IS_RELATIVE_PROMPT.format(old_prd=old_prd_doc.content, requirements=new_requirement_doc.content)
        res = await self._aask(prompt=prompt)
        logger.info(f"REQ-RELATIVE: [{new_requirement_doc.root_relative_path}, {old_prd_doc.root_relative_path}]: {res}")
        if "YES" in res:
            return True
        return False

    async def _merge(self, new_requirement_doc, prd_doc, format=CONFIG.prompt_format) -> Document:
        if not CONFIG.project_name:
            CONFIG.project_name = Path(CONFIG.project_path).name
        prompt = MERGE_PROMPT.format(
            requirements=new_requirement_doc.content, old_prd=prd_doc.content, project_name=CONFIG.project_name
        )
        prd = await self._aask_v1(prompt, "prd", OUTPUT_MAPPING, format=format)
        prd_doc.content = prd.instruct_content.json(ensure_ascii=False)
        await self._rename_workspace(prd)
        return prd_doc

    async def _update_prd(self, requirement_doc, prd_doc, prds_file_repo, *args, **kwargs) -> Document | None:
        if not prd_doc:
            prd = await self._run_new_requirement(requirements=[requirement_doc.content], *args, **kwargs)
            new_prd_doc = Document(
                root_path=PRDS_FILE_REPO,
                filename=FileRepository.new_filename() + ".json",
                content=prd.instruct_content.json(ensure_ascii=False),
            )
        elif await self._is_relative_to(requirement_doc, prd_doc):
            new_prd_doc = await self._merge(requirement_doc, prd_doc)
        else:
            return None
        await prds_file_repo.save(filename=new_prd_doc.filename, content=new_prd_doc.content)
        await self._save_competitive_analysis(new_prd_doc)
        await self._save_pdf(new_prd_doc)
        return new_prd_doc

    @staticmethod
    async def _save_competitive_analysis(prd_doc):
        m = json.loads(prd_doc.content)
        quadrant_chart = m.get("Competitive Quadrant Chart")
        if not quadrant_chart:
            return
        pathname = (
                CONFIG.git_repo.workdir / Path(COMPETITIVE_ANALYSIS_FILE_REPO) / Path(prd_doc.filename).with_suffix("")
        )
        if not pathname.parent.exists():
            pathname.parent.mkdir(parents=True, exist_ok=True)
        await mermaid_to_file(quadrant_chart, pathname)

    @staticmethod
    async def _save_pdf(prd_doc):
        await FileRepository.save_as(doc=prd_doc, with_suffix=".md", relative_path=PRD_PDF_FILE_REPO)

    @staticmethod
    async def _rename_workspace(prd):
        if CONFIG.project_path:  # Updating on the old version has already been specified if it's valid. According to
            # Section 2.2.3.10 of RFC 135
            if not CONFIG.project_name:
                CONFIG.project_name = Path(CONFIG.project_path).name
                return

        if not CONFIG.project_name:
            if isinstance(prd, ActionOutput):
                ws_name = prd.instruct_content.dict()["Project Name"]
            else:
                ws_name = CodeParser.parse_str(block="Project Name", text=prd)
            CONFIG.project_name = ws_name
        CONFIG.git_repo.rename_root(CONFIG.project_name)

    async def _is_bugfix(self, content):
        prompt = IS_BUGFIX_PROMPT.format(content=content)
        res = await self._aask(prompt=prompt)
        logger.info(f"IS_BUGFIX:{res}")
        if "YES" in res:
            return True
        return False
