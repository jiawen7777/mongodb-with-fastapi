import os
import shutil
from typing import Optional, List

from fastapi import FastAPI, Body, HTTPException, status
from fastapi.responses import Response
from pydantic import ConfigDict, BaseModel, Field, EmailStr
from pydantic.functional_validators import BeforeValidator
from starlette.middleware.cors import CORSMiddleware

from typing_extensions import Annotated
from datetime import datetime
from bson import ObjectId
import motor.motor_asyncio
from pymongo import ReturnDocument

from algorithm.file_tree_util import get_file_tree

app = FastAPI(
    title="Markdown Editor API",
    summary="A sample application showing how to use FastAPI to add a RESTful API to a MongoDB collection.",
)

origins = ["http://localhost:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
client = motor.motor_asyncio.AsyncIOMotorClient(
    "mongodb://localhost:27017/?readPreference=primary&ssl=false&directConnection=true")
db = client.my_note
markdown_collection = db.get_collection("markdown")

# Represents an ObjectId field in the database.
# It will be represented as a `str` on the model so that it can be serialized to JSON.
PyObjectId = Annotated[str, BeforeValidator(str)]

root_path = "/Users/jiawen/Documents/markdown-editor"


class MarkdownModel(BaseModel):
    """
    Container for a single markdown record.
    """

    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    content: str
    file_name: str
    creator: str = Field(default="admin")
    date_added: datetime = Field(default_factory=datetime.utcnow)
    date_modified: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        # 确保别名字段（如_id）在JSON序列化和反序列化时都使用
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {
            datetime: lambda v: v.strftime('%Y-%m-%d %H:%M:%S')
        }
        schema_extra = {
            "example": {
                "file_name": "test_file.md",
                "content": "This is the content...",
                "creator": "admin",
                "date_added": "2023-02-21 12:13:34",
                "date_modified": "2023-02-21 12:13:34",
            }
        }


class UpdateMarkdownModel(BaseModel):
    """
    A set of optional updates to be made to a document in the database.
    """

    file_path: Optional[str] = None
    file_name: Optional[str] = None
    creator: Optional[str] = None
    date_added: Optional[datetime] = None
    date_modified: Optional[datetime] = Field(default_factory=datetime.utcnow)
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        json_encoders={
            datetime: lambda v: v.strftime('%Y-%m-%d %H:%M:%S')
        },
        json_schema_extra={
            "example": {
                "file_name": "test_file.md",
                "file_path": "~/data/mkdown",
                "creator": "admin",
                "date_added": "2023-02-21 12:13:34",
                "date_modified": "2023-02-21 12:13:34",
            }
        }
    )


class MarkdownCollection(BaseModel):
    """
    A container holding a list of `markdownModel` instances.

    This exists because providing a top-level array in a JSON response can be a [vulnerability](https://haacked.com/archive/2009/06/25/json-hijacking.aspx/)
    """

    markdowns: List[MarkdownModel]


@app.post(
    "/markdowns/",
    response_description="Add new markdown file",
    response_model=MarkdownModel,
    status_code=status.HTTP_201_CREATED,
    response_model_by_alias=False,
)
async def create_markdown(markdown: MarkdownModel = Body(...)):
    """
    Insert a new markdown record.

    A unique `id` will be created and provided in the response.
    """
    new_markdown = await markdown_collection.insert_one(
        markdown.model_dump(by_alias=True, exclude=["id"])
    )
    created_markdown = await markdown_collection.find_one(
        {"_id": new_markdown.inserted_id}
    )
    return created_markdown


@app.get(
    "/markdowns/",
    response_description="List all markdown files",
    response_model=MarkdownCollection,
    response_model_by_alias=False,
)
async def list_markdowns():
    """
    List all the markdown data in the database.

    The response is unpaginated and limited to 1000 results.
    """
    return MarkdownCollection(markdowns=await markdown_collection.find().to_list(1000))


@app.get(
    "/markdowns/{id}",
    response_description="Get a single markdown",
    response_model=MarkdownModel,
    response_model_by_alias=False,
)
async def show_markdown(id: str):
    """
    Get the record for a specific markdown, looked up by `id`.
    """
    if (
            markdown := await markdown_collection.find_one({"_id": ObjectId(id)})
    ) is not None:
        return markdown

    raise HTTPException(status_code=404, detail=f"markdown {id} not found")


@app.put(
    "/markdowns/{id}",
    response_description="Update a markdown",
    response_model=MarkdownModel,
    response_model_by_alias=False,
)
async def update_markdown(id: str, markdown: UpdateMarkdownModel = Body(...)):
    """
    Update individual fields of an existing markdown record.

    Only the provided fields will be updated.
    Any missing or `null` fields will be ignored.
    """
    markdown = {
        k: v for k, v in markdown.model_dump(by_alias=True).items() if v is not None
    }

    if len(markdown) >= 1:
        update_result = await markdown_collection.find_one_and_update(
            {"_id": ObjectId(id)},
            {"$set": markdown},
            return_document=ReturnDocument.AFTER,
        )
        if update_result is not None:
            return update_result
        else:
            raise HTTPException(status_code=404, detail=f"markdown {id} not found")

    # The update is empty, but we should still return the matching document:
    if (existing_markdown := await markdown_collection.find_one({"_id": id})) is not None:
        return existing_markdown

    raise HTTPException(status_code=404, detail=f"markdown {id} not found")


@app.delete("/markdowns/{id}", response_description="Delete a markdown")
async def delete_markdown(id: str):
    """
    Remove a single markdown record from the database.
    """
    delete_result = await markdown_collection.delete_one({"_id": ObjectId(id)})

    if delete_result.deleted_count == 1:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    raise HTTPException(status_code=404, detail=f"markdown {id} not found")


class NodeItem(BaseModel):
    path: str
    name: str


def create_folder(path):
    # os.makedirs 可以创建多层级的文件夹，exist_ok=True 表示如果文件夹存在就忽略
    os.makedirs(path, exist_ok=True)


def create_file(file_path):
    # 使用 with 语句确保文件正确关闭
    with open(file_path, 'w') as file:
        file.write('')  # 创建文件时可以写入一些初始内容


class FileRequest(BaseModel):
    path: str


class FileContent(BaseModel):
    path: str
    content: str



@app.get("/folder-items")
async def get_folder_items(path: str):
    return get_file_tree(path)


@app.post("/file")
async def get_folder_items(node_item: NodeItem):
    file_path = os.path.join(root_path, node_item.path, node_item.name)
    create_file(file_path)
    return "ok"


@app.post("/folder")
async def get_folder_items(node_item: NodeItem):
    folder_path = os.path.join(root_path, node_item.path, node_item.name)
    create_folder(folder_path)
    return "ok"


@app.post("/get-file-content/")
async def get_file_content(file_request: FileRequest):
    file_path = os.path.join(root_path, file_request.path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        with open(file_path, "r", encoding="utf-8") as file:
            content = file.read()
            return {"content": content}
    return {"content": "", "error": "File does not exist or is not a file."}


@app.post("/save-file")
async def save_file(file_content: FileContent):
    try:
        # 根据需要修改路径
        full_path = os.path.join(root_path, file_content.path)
        print(full_path)

        with open(full_path, "w") as f:
            f.write(file_content.content)
        return {"message": "File saved successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/delete/")
async def delete_file_or_directory(path: str):
    # 解码路径
    file_path = os.path.join(root_path, path)

    # 检查路径是否存在
    try:
        if os.path.isdir(file_path):
            # 它是一个目录，使用shutil.rmtree进行删除
            shutil.rmtree(file_path)
        else:
            os.remove(file_path)
    except Exception as e:
        # 如果在删除过程中发生错误，返回500错误
        raise HTTPException(status_code=500, detail=str(e))

    return {"detail": "Item deleted successfully"}
