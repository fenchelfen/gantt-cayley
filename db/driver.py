from gantt_cayley.gc_pyley.pyley import CayleyClient, GraphObject
from .models import User, Group, Task, Project
import requests
import re

class DatabaseDriver():
    types = {
        "USER": User,
        "GROUP": Group,
        "PROJECT": Project,
        "TASK": Task
    }

    labels = {
        type(User()): ("USER", "username"),
        type(Group()): ("GROUP" "name"),
        type(Project()): ("PROJECT", "name"),
        type(Task()): ("TASK", "title")
    }

    def __init__(self, address=""):

        self.client = CayleyClient(limit=-1) if address == "" else CayleyClient(url=address, limit=-1)
        self.g = GraphObject()

    def get_user_by_id(self, user_id):
        query = self.g.V("user/" + str(user_id)).Out(["username", "password", "email", "in_group"], "pred").All()

        try:
            response = self.client.Send(query).result["result"]
            user = User(user_id)
            for i in response:
                if i['pred'] == 'in_group':
                    id_parsed = int(i['id'].split('/')[1])
                    setattr(user, i['pred'], getattr(user, i['pred']) + [id_parsed])
                else:
                    setattr(user, i['pred'], i['id'])

            return user

        except:
            return None

    def _update_attr(self, obj, dict):
        if type(getattr(obj, dict['pred'])) == type([]):
            if not re.findall("\d+", dict['id'])[0] in getattr(obj, dict['pred']):
                getattr(obj, dict['pred']).append(re.findall("\d+", dict['id'])[0])
        else:
            setattr(obj, dict['pred'], dict['id'])

    def get_object_by_id(self, object_type, object_id):

        obj_id = object_type.lower() + "/" + str(object_id)
        return self._get_object_by_id(obj_id)

    # object_id in form "type/id"
    def _get_object_by_id(self, object_id):
        pattern = re.findall(re.compile("[a-z]+"), object_id)

        if len(pattern) != 1:
            return None
        label = pattern[0].upper()
        
        if label in self.types:
            query = self.g.V(object_id).Out(tags="pred").All()

            try:
                response = self.client.Send(query).result["result"]
                
                new_object = self.types[label](re.findall("\d+", object_id)[0])
                
                for i in response:
                    self._update_attr(new_object, i)
            except: 
                return None

            return new_object

        return None

    def _transform_to_json(self, response):
        
        json_objects = {}

        for record in response:
            oid, pred, source_id = record['id'], record['pred'], record['source_id']
            if source_id in json_objects:
                if pred in json_objects[source_id]:
                    if type(json_objects[source_id][pred]) == type([]):
                        json_objects[source_id][pred].append(oid)
                    else:
                        json_objects[source_id][pred] = [json_objects[source_id][pred], oid]
                else:
                    json_objects[source_id][pred] = oid
            else:
                json_objects[source_id] = {pred: oid}

        return json_objects


    def _parse_object_response(self, response):
        objects = []
        json = self._transform_to_json(response)
        for key, value in json.items():
            label = re.findall(re.compile("[a-z]+"), key)[0].upper()
            id_ = int(re.findall(re.compile("\d+"), key)[0])

            obj = self.types[label](**value)
            obj.id = id_
            objects.append(obj)
        
        return objects


    def filter_by(self, **kwargs):

        if "type" in kwargs:
            label = kwargs.pop("type").upper()
            if label in self.types:
                query_templ = "g.V().LabelContext(\"%s\").In().LabelContext(null)" % (label)
                query = "g.V().LabelContext(\"%s\").In().Tag(\"source_id\").LabelContext(null)" % (label)
            else:
                return []

        else:
            query_templ = "g.V()"
            query = "g.V().Tag(\"source_id\")"

        query_end = ".Out([], \"pred\").All()"        
        if len(kwargs) > 0:
            key, value = kwargs.popitem()
            query = "%s.Has(\"%s\", \"%s\")" % (query, key, value)

        for key, value in kwargs.items():
            if key == "type":
                return []
            
            query_step = ".And(%s.Has(\"%s\", \"%s\"))" % (query_templ, key, value)
            
            query = "{}{}".format(query, query_step)

        query = "{}{}".format(query, query_end)

        try:
            response = self.client.Send(query).result["result"]
            return self._parse_object_response(response)
        except Exception as e:
            print(e.with_traceback)
            return []

    def _get_last_id_from_db(self, label):
        query = self.g.V(label).Out("last_id").All()
        response = self.client.Send(query).result['result']
        return int(response[0]['id']) if response != None else 0

    def _generate_new_id(self, label, type_):
        
        last_from_db = self._get_last_id_from_db(label)

        if last_from_db == 0:
            new_id = 1
        else: 
            new_id = last_from_db + 1
            self.client.DeleteQuad(label, "last_id", str(last_from_db))

        while True:
            query = self.g.V(type_+"/"+str(new_id)).All()
            response = self.client.Send(query).result['result']
            if response == None:
                break
            new_id += 1
         
        self.client.AddQuad(label, "last_id", str(new_id))

        return new_id

    # action should be "add" or "delete"
    def _generate_quads(self, object_, action, last_used_id = 0):
        attrs = object_.__dict__.items()

        quads = []

        object_id = last_used_id

        if type(object_) in self.labels:
            label = self.labels[type(object_)][0]
            label_position = self.labels[type(object_)][1]
            type_ = label.lower()

            if action == "add":
                object_id = self._generate_new_id(label, type_)
            elif action == "delete":
                object_id = getattr(object_, "id")
            else: 
                return []

            str_id = type_+"/"+str(object_id)
            object_.id = object_id

            for key, value in attrs:
                if key != "id" and value != None and value != []:
                    if  key == label_position:
                        quad = (str_id, key, value, label)
                    else: 
                        quad = (str_id, key, value)
                    quads.append(quad)

        return quads

    def add_object(self, object_):
        self.add_objects([object_])

    def add_objects(self, objects): 
        quads = []
        for obj in objects:
            quads += self._generate_quads(obj, "add")

        self.client.AddQuads(quads)

    def edit(self, old_object, new_object):
        old = self._generate_quads(old_object, "delete")
        new = self._generate_quads(new_object, "delete")

        self.client.DeleteQuads(old).result['result']
        self.client.AddQuads(new)

    def _update_last_used_id(self, quads):
        checked = []
        for q in quads:
            if not q[0] in checked:
                checked.append(q[0])
                type_ = re.findall(re.compile("[a-z]+"), q[0])[0]
                id_ = int(re.findall(re.compile("\d+"), q[0])[0])
                label = type_.upper()
                last_id = self._get_last_id_from_db(label)
                if id_ <= last_id:
                    self.client.DeleteQuad(label, "last_id", str(last_id))
                    self.client.AddQuad(label, "last_id", str(id_-1))               
                                
    def delete_object(self, object_):
        self.delete_objects([object_])

    def delete_objects(self, objects):
        quads = []

        for obj in objects:
            quads += self._generate_quads(obj, "delete")
        
        self.client.DeleteQuads(quads)
        self._update_last_used_id(quads)

    def add_task(self, project_id, task):
        self.add_object(task)

        self.client.AddQuad("project/%d"%project_id, "task", "task/%d"%task.id)
