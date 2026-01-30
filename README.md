# Confantic

Confantic is a lightweight, text-based user interface to edit YAML and JSON configuration files with real-time validation and feedback.

YAML and JSON configuration files are all over the place. For less polished workflows, they can become a sort of "user interface" into the configuration of system.
Expecting users to fill out text files to modify configuration is an extremely easy thing to develop, but has obvious UX limitations; the most notable of which is **user's often don't know which fields are expected and their constraints**.
Confantic seeks to address this and take configuration files as UI a little more seriously.

## Installation

`pip install confantic`

## Usage

Confantic is built on top of [Pydantic](<[url](https://docs.pydantic.dev/latest/)>) to define the configuration model. To use it, you first need a pydantic model to validate against. Lets use this one as an example:

model.py

```python
from pydantic import BaseModel


class ProgramConfig(BaseModel):
    name: str
    version: str
    debug: bool = False
```

To specify which model to use when editing, you use a **Model URI** that tells python how to import the model. It supports two different specifications:

1. &lt;file path&gt;:&lt;model class&gt; (ex. ./my_folder/my_file.py:MyModel)
2. &lt;module path&gt;:&lt;model class&gt; (ex. my_module.my_submodule:MyModel)

Now, we can run the following command to start creating a config:

```
confantic model.py:ProgramConfig config.json
```

![image](https://github.com/user-attachments/assets/c5ea056e-3d49-48fc-a66d-ebcd8c08e82c)

If the target file (`config.json` in this case) does not exist, it will populate the editor with some attempted defaults for the field - to at least give you the structure of the model.
If we change some of the fields to create an error, we see the error show up at the bottom:

![image](https://github.com/user-attachments/assets/3da4a8a2-0d72-481d-a001-6286ba43e474)
