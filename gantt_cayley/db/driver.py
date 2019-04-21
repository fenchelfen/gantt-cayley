from pyley import CayleyClient, GraphObject
import requests
from models import *

class DatabaseDriver():
    
    types = {
            "USER": User,
            "GROUP": Group,
            "PROJECT": Project,
            "TASK": Task
        }

    def __init__(self, address=""):

        self.client = CayleyClient()
        self.g = GraphObject()

    def get_user_by_id(self, id):
        query = self.g.V("user:"+str(id)).Out(["username", "password", "email", "in_group"], "pred").All()
        response = self.client.Send(query)
        return response.result["result"]

    def _parse_object_response(self, response, label):
        created_objects = []
        objects = []
        for i in response:
            if not i['source_id'] in created_objects:
                objects.append(self.types[label](i['source_id']))
                created_objects.append(i['source_id'])
            user = next((x for x in objects if x.id == i['source_id']), None)
            if type(getattr(user, i['pred'])) == type(set()):
                getattr(user, i['pred']).add(i['id'])
            else: 
                setattr(user, i['pred'], i['id'])

        return objects

    def _filter_by_label(self, label):

        query = "g.V().LabelContext(\"%s\").In().Tag(\"source_id\").LabelContext(null) \
            .Out([], \"pred\").All()" % (label)  

        response = self.client.Send(query).result["result"] 

        return self._parse_object_response(response, label)

    def _filter_by_parameter(self, parameter, value=None):
        if value is None:
            query = self.g.V().Out(parameter).All()
        else:
            query = self.g.V().Both(parameter).Is(*value).All()

        response = self.client.Send(query).result["result"]
        return set((i['id'] for i in response))
    

    def filter_by(self, node_type, value=None):

        upper_node_type = node_type.upper()

        if upper_node_type in self.types:
            result = self._filter_by_label(upper_node_type)
            
        else:
            result = self._filter_by_parameter(node_type, value)
        
        return None or result

