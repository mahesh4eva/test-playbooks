from common.api import resources
import base


class ActivityStream(base.Base):

    pass

base.register_page(resources.v1_activity, ActivityStream)


class ActivityStreams(ActivityStream, base.BaseList):

    pass

base.register_page([resources.v1_activity_stream,
                    resources.v1_object_activity_stream], ActivityStreams)

# backwards compatibility
Activity_Page = ActivityStream
Activity_Stream_Page = ActivityStreams
