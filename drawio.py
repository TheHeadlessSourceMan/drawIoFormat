"""
open/save the draw.io diagram drawing format
"""
import typing
import base64
import zlib
from urllib.parse import unquote,quote
import lxml.etree


class MxItem:
    """
    base class for mx items
    """
    def __init__(self,
        fileParent:typing.Optional["MxItem"],
        xmlTag:lxml.etree.Element):
        """ """
        self._fileChildren:typing.List["MxItem"]=[]
        self._parent:typing.Optional["MxItem"]=None
        self._children:typing.List["MxItem"]=[]
        self._root:"MxItem"=self
        self._fileRoot:typing.Optional["MxItem"]=None
        self.fileParent:typing.Optional["MxItem"]=fileParent # the parent in the xml hierarchy # noqa: E501 # pylint: disable=line-too-long
        self._xmlTag:lxml.etree.Etree=xmlTag

    @property
    def mxType(self):
        """
        what type this item is
        """
        return self._xmlTag.tag

    @property
    def mxId(self):
        """
        the unique id of this item
        """
        return self._xmlTag.attrib.get('id')
    @property
    def id(self):
        """
        the unique id of this item
        """
        return self.mxId

    @property
    def name(self):
        """
        a friendly, printable name for this node
        """
        v=self._xmlTag.attrib.get('value')
        if v is None:
            return self.mxType
        return '%s "%s"'%(self.mxType,v)

    @property
    def value(self):
        """
        for instance the text of a textbox
        """
        return self._xmlTag.attrib.get('value')

    @property
    def fileRoot(self):
        """
        the root in the xml hierarchy
        """
        if self._fileRoot is None:
            if self.fileParent is not None:
                self._fileRoot=self.fileParent.fileRoot
        return self._fileRoot

    @property
    def fileChildren(self)->typing.Iterable["MxItem"]:
        """
        the children in the xml hierarchy
        """
        return self._fileChildren

    @property
    def root(self)->"DrawIoFile":
        """
        this is the root in terms of the logical diagram connections,
        as opposed to the root in the xml hierarchy (self.fileRoot),
        which is totally different
        """
        if self._root is None:
            p=self.parent
            if p is not None:
                self._root=p.root
        return self._root # type: ignore

    @property
    def parent(self):
        """
        this is the parent in terms of the logical diagram connections,
        as opposed to the parent in the xml hierarchy (self.fileParent),
        which is totally different
        """
        parentId=self._xmlTag.attrib.get('parent')
        if self._parent is None or self._parent.id!=parentId:
            if parentId is None:
                self._parent=None
            else:
                self._parent=self.fileRoot.lookupId(parentId)
        return self._parent

    @property
    def children(self)->typing.Iterable["MxItem"]:
        """
        this is the children in terms of the logical diagram connections,
        as opposed to the children in the xml hierarchy
        """
        if not self._children and self.name=='root':
            return self.fileChildren
        return self._children

    def __iter__(self)->typing.Iterable["MxItem"]:
        return iter(self.children)

    def __getitem__(self,
        idx:typing.Union[int,slice]
        )->typing.Union["MxItem",typing.Iterable["MxItem"]]:
        _=self.children # force load
        return self._children[idx]

    def walkFileTree(self)->typing.Generator["MxItem",None,None]:
        """
        walk the file tree(deapth-first) and yeild each mxItem
        """
        yield self
        for c in self.fileChildren:
            yield from c.walkFileTree()

    @property
    def xmlTag(self):
        """
        xml tag associated with this item
        """
        return self._xmlTag
    @xmlTag.setter
    def xmlTag(self,xmlTag):
        self._xmlTag=xmlTag
        self._fileChildren=[MxItem(self,childXml) for childXml in xmlTag]

    def treeStr(self,indent='',ignore=None):
        """
        a printable tree outlining the logical structure
        """
        ret=[indent+self.name]
        indent+='   '
        if ignore is None:
            ignore=set([self])
        elif self in ignore:
            ret.append('...')
        else:
            for c in self.children:
                ret.append(c.treeStr(indent,ignore))
        return indent.join(ret)


class DrawIoFile:
    """
    open/save the draw.io diagram drawing format
    """

    def __init__(self,filename:str):
        self._itemTree:typing.Optional[MxItem]=None
        self._itemLookup:typing.Dict[str,MxItem]={} # handy table to look up items by id # noqa: E501 # pylint: disable=line-too-long
        self._etree:typing.Any=None
        self.load(filename)

    def treeStr(self,indent='',ignore=None):
        """
        Get a string formatted in a visually tree-like way
        """
        # assumes the first item under <root> is the top of the tree
        return self._itemTree[0].treeStr(indent,ignore)

    def load(self,filename:str):
        """
        load an encoded .drawio file or a non-encoded .xml file
        (determines this by the file extension)
        """
        f=open(filename,'rb')
        data=f.read().decode('utf-8')
        f.close()
        self.assign(data,filename.rsplit('.',1)[-1]=='drawio')

    def _mxDecodeBlock(self,b:typing.Union[str,bytes])->str:
        """
        decode a single block of compressessed mxfile schmutz

        TODO: NOTE: IMPORTANT: KURT:
          read this!
          https://towardsdatascience.com/all-the-ways-to-compress-and-archive-files-in-python-e8076ccedb4b

        NOTE: see
            https://stackoverflow.com/questions/70175214/opening-a-draw-io-file-using-python
        """
        if isinstance(b,str):
            b=b.encode('utf-8')
        s=base64.b64decode(b)
        b=zlib.decompress(s,wbits=-15)
        s=unquote(b.decode('utf-8'))
        return s

    def _mxEncodeBlock(self,s:str)->str:
        """
        encode a single block of compressessed mxfile
        """
        b=quote(s)
        b=zlib.compress(b,wbits=-15)
        s=base64.b64encode(b)
        return s

    @property
    def decoded(self)->str:
        """
        get the current file as a decoded string
        """
        return lxml.etree\
            .tostring(self._etree,pretty_print=True)\
            .decode('utf-8')\
            .strip()

    @property
    def encoded(self)->str:
        """
        get the current file as an encoded string
        """
        raise NotImplementedError()

    def lookupId(self,mxId:str)->typing.Optional[MxItem]:
        """
        Lookup an item by id
        """
        return self._itemLookup.get(mxId)

    def assign(self,s:str,encoded=True,keepMxfileTag:bool=True):
        """
        assign this object to some xml
        """
        if encoded:
            name='diagram'#'mxfile'
            decoded:typing.List[str]=[]
            for mx in s.split('<'+name):
                if not decoded:
                    # first time around is stuff before the mx tag
                    decoded.append(mx)
                    if keepMxfileTag:
                        decoded.append('<'+name)
                else:
                    mxs=mx.split('>',1)
                    if keepMxfileTag:
                        decoded.append(mxs[0])
                        decoded.append('>')
                    mxs=mxs[1].split('</'+name+'>',1)
                    decoded.append(self._mxDecodeBlock(mxs[0]))
                    if keepMxfileTag:
                        decoded.append('</'+name+'>')
                    decoded.append(mxs[1])
            s=''.join(decoded)
        self._etree=lxml.etree.fromstring(s)
        self._itemTree=MxItem(None,self._etree[0][0][0])
        self._itemTree._fileRoot=self # pylint: disable=protected-access
        self._relinkAll()

    def _relinkAll(self):
        """
        since each of the mx items specify only the parent, we need to
        fly through everything and link children to their parents
        """
        self._itemLookup={}
        for item in self._itemTree.walkFileTree():
            self._itemLookup[item.id]=item
        # now that everything is added, we can link it up
        for item in self._itemLookup.values():
            if item.parent is not None:
                item.parent._children.append(item) # noqa: E501 # pylint: disable=line-too-long,protected-access

    def __str__(self)->str:
        """
        this in string form
        (same as self.decoded)
        """
        return self.decoded


def cmdline(args:typing.Iterable[str])->int:
    """
    Run this like from the commadn line
    """
    printhelp=False
    for arg in args:
        if arg.startswith('-'):
            kv=arg.split('=',1)
            if kv[0] in ('--help','-h'):
                printhelp=True
            elif arg[0]=='--encode':
                mx=DrawIoFile(kv[1])
                print(mx.encoded)
            elif kv[0]=='--kv':
                mx=DrawIoFile(arg[1])
                print(mx.decoded)
            elif kv[0]=='--tree':
                mx=DrawIoFile(kv[1])
                print(mx.treeStr())
            else:
                print('ERR: Unknown Argument "%s"'%arg)
                printhelp=True
        else:
            filename=arg
            mx=DrawIoFile(filename)
            if filename.endswith('.drawio'):
                # we are decoding
                print(mx.decoded)
            else:
                # we are encoding
                print(mx.encoded)
    if printhelp:
        print('Useage:')
        print('   drawio.py [options] [encode.xml | decode.drawio]')
        print('Options:')
        print('   --help ......... show this help')
        print('   --encode=file .. encode a file')
        print('   --decode=file .. decode a file')
        print('   --tree=file .... show the logical file tree')
        return -1
    return 0


if __name__=='__main__':
    import sys
    sys.exit(cmdline(sys.argv[1:]))
