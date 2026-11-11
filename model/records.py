class Record:
    def __init__(self, record_id: int, record_type: str):
        self.id = record_id
        self.type = record_type

    def to_dict(self):
        return {"id": self.id, "type": self.type}


class Note(Record):
    def __init__(self, record_id: int, text: str):
        super().__init__(record_id, "note")
        self.text = text

    def update(self, text: str = None):
        if text is not None:
            self.text = text

    def to_dict(self):
        data = super().to_dict()
        data["text"] = self.text
        return data


class Task(Record):
    def __init__(self, record_id: int, description: str, deadline: str):
        super().__init__(record_id, "task")
        self.description = description
        self.deadline = deadline

    def update(self, description: str = None, deadline: str = None):
        if description is not None:
            self.description = description
        if deadline is not None:
            self.deadline = deadline

    def to_dict(self):
        data = super().to_dict()
        data["description"] = self.description
        data["deadline"] = self.deadline
        return data


class Event(Record):
    def __init__(self, record_id: int, description: str, start: str, alarm: str):
        super().__init__(record_id, "event")
        self.description = description
        self.start = start
        self.alarm = alarm

    def update(self, description: str = None, start: str = None, alarm: str = None):
        if description is not None:
            self.description = description
        if start is not None:
            self.start = start
        if alarm is not None:
            self.alarm = alarm

    def to_dict(self):
        data = super().to_dict()
        data["description"] = self.description
        data["start"] = self.start
        data["alarm"] = self.alarm
        return data


class Contact(Record):
    def __init__(self, record_id: int, name: str, address: str, mobile: str):
        super().__init__(record_id, "contact")
        self.name = name
        self.address = address
        self.mobile = mobile

    def update(self, name: str = None, address: str = None, mobile: str = None):
        if name is not None:
            self.name = name
        if address is not None:
            self.address = address
        if mobile is not None:
            self.mobile = mobile

    def to_dict(self):
        data = super().to_dict()
        data["name"] = self.name
        data["address"] = self.address
        data["mobile"] = self.mobile
        return data