import hou

Primitive = 1
Point = 2
Edge = 4
Vertex = 8
Detail = 4


def readDetailIntrinsic(node_or_geo, name):
    if isinstance(node_or_geo, str):
        return readDetailIntrinsic(hou.node(node_or_geo), name)
    elif isinstance(node_or_geo, hou.Node):
        geo = node_or_geo.geometry()
        if geo is None:
            return ()
        else:
            return readDetailIntrinsic(geo, name)
    elif isinstance(node_or_geo, hou.Geometry):
        return node_or_geo.intrinsicValue(name)
    return ()


def forceTuple(func):
    def wrapper(*args, **kwargs):
        res = func(*args, **kwargs)
        if not isinstance(res, tuple):
            return res,
        else:
            return res

    return wrapper


@forceTuple
def primitiveGroups(node_or_geo):
    return readDetailIntrinsic(node_or_geo, 'primitivegroups')


@forceTuple
def pointGroups(node_or_geo):
    return readDetailIntrinsic(node_or_geo, 'pointgroups')


@forceTuple
def edgeGroups(node_or_geo):
    return readDetailIntrinsic(node_or_geo, 'edgegroups')


@forceTuple
def vertexGroups(node_or_geo):
    return readDetailIntrinsic(node_or_geo, 'vertexgroups')


def groups(node_or_geo, group_type=Primitive | Point | Edge | Vertex):
    group_list = []
    if group_type & Primitive:
        group_list.extend(primitiveGroups(node_or_geo))
    if group_type & Point:
        group_list.extend(pointGroups(node_or_geo))
    if group_type & Edge:
        group_list.extend(edgeGroups(node_or_geo))
    if group_type & Vertex:
        group_list.extend(vertexGroups(node_or_geo))
    return tuple(group_list)


def groupMenu(node, input_index=0, group_type=Primitive | Point | Edge | Vertex):
    menu = []
    if isinstance(node, str):
        node = hou.node(node)
    inputs = node.inputs()
    if inputs and len(inputs) > input_index and inputs[input_index]:
        group_list = groups(inputs[input_index], group_type)
        for group in group_list:
            menu.extend((group, group))
    return tuple(menu)


@forceTuple
def primitiveAttribs(node_or_geo):
    return readDetailIntrinsic(node_or_geo, 'primitiveattributes')


@forceTuple
def pointAttribs(node_or_geo):
    return readDetailIntrinsic(node_or_geo, 'pointattributes')


@forceTuple
def vertexAttribs(node_or_geo):
    return readDetailIntrinsic(node_or_geo, 'vertexattributes')


@forceTuple
def detailAttribs(node_or_geo):
    return readDetailIntrinsic(node_or_geo, 'detailattributes')


def attribs(node_or_geo, attrib_type=Primitive | Point | Vertex | Detail):
    attrib_list = []
    if attrib_type & Primitive:
        attrib_list.extend(primitiveAttribs(node_or_geo))
    if attrib_type & Point:
        attrib_list.extend(pointAttribs(node_or_geo))
    if attrib_type & Vertex:
        attrib_list.extend(vertexAttribs(node_or_geo))
    if attrib_type & Detail:
        attrib_list.extend(detailAttribs(node_or_geo))
    return tuple(attrib_list)


def attribMenu(node, input_index=0, attrib_type=Primitive | Point | Vertex | Detail):
    menu = []
    if isinstance(node, str):
        node = hou.node(node)
    inputs = node.inputs()
    if inputs and len(inputs) > input_index and inputs[input_index]:
        attrib_list = attribs(inputs[input_index], attrib_type)
        for attrib in attrib_list:
            menu.extend((attrib, attrib))
    return tuple(menu)


def primitiveCount(node_or_geo):
    return readDetailIntrinsic(node_or_geo, 'primitivecount')


def pointCount(node_or_geo):
    return readDetailIntrinsic(node_or_geo, 'pointcount')


def edgeCount(node_or_geo):
    raise NotImplementedError('Impossible')


def vertexCount(node_or_geo):
    return readDetailIntrinsic(node_or_geo, 'vertexcount')
