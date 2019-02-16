"""Module for the Lifemapper TreeWrapper class

Todo:
    * Should we provide a method to collapse clades that only have one child?
    * Add method to remove annotations
    * Move label method out of internal functions
"""
import dendropy
import numpy as np

from analyses.lm_objects.matrix import Matrix


# .............................................................................
# .                     Phylogenetic Tree Module Constants                    .
# .............................................................................
DEFAULT_TREE_SCHEMA = 'nexus'


# .............................
class PhyloTreeKeys(object):
    """Keys for phylogenetic trees
    """
    MTX_IDX = 'mx'  # The matrix index for this node
    SQUID = 'squid'  # This is the LM SQUID (species identifier) for the tip


# .............................................................................
class LmTreeException(Exception):
    """Wrapper around the base Exception class for tree related errors
    """
    pass


# .............................................................................
class TreeWrapper(dendropy.Tree):
    """Dendropy Tree wrapper

    Dendropy tree wrapper that adds a little functionality and improves
    performance of some functions
    """
    # ..............................
    @classmethod
    def from_base_tree(cls, tree):
        """Creates a TreeWrapper object from a base dendropy.Tree
        """
        return cls.get(data=tree.as_string('nexus'), schema='nexus')

    # ..............................
    def add_node_labels(self, prefix=None, overwrite=False):
        """Add labels to the nodes in the tree

        Add labels to the unlabeled nodes in the tree.

        Args:
            prefix (:obj:`str`, optional): If provided, prefix the node labels
                with this string.
            overwrite (boolean): Indicates whether existing node labels should
                be overwritten or if they should be maintained.

        Note:
            This labels nodes the way that R does
        """
        self._label_tree_nodes(self.seed_node, len(self.get_labels()),
                               prefix=prefix, overwrite=overwrite)

    # ..............................
    def annotate_tree(self, annotation_dict, annotation_attribute=None,
                      label_attribute=None, update=False):
        """Annotates tree tips and nodes

        Args:
            annotation_dict (:obj:`dict`): A dictionary where the keys
                correspond with the node labels and the value is either, a
                single value, or a dictionary of annotation name keys and
                annotation value values.
            annotation_attribute (:obj:`str` or None, optional): Only used if
                annotation_dict contains single values, this will be the name
                of the annotation added for each node.  Using None or setting
                value to 'label' will change the label of the node.
            label_attribute (:obj:`str`, optional): Use the value of this
                annotation as the label for the node.  Setting the value to
                'label' or leaving as None will use the label of the node.
            update (:obj:`bool`, optional): If True, update any existing
                annotations with the annotations provided.
        """
        label_method = self._get_label_method(label_attribute)

        for node in self.nodes():
            # Get the label of the node
            label = label_method(node)
            if label in annotation_dict.keys():
                node_annotation = annotation_dict[label]

                # Assume annotations are in a dictionary
                try:
                    for (ann_name, ann_value) in node_annotation.items():
                        self._annotate_node(
                            node, ann_name, ann_value, update=update)
                except Exception:
                    # Annotation is a single value
                    self._annotate_node(
                        node, annotation_attribute, node_annotation,
                        update=update)

    # ..............................
    def annotate_tree_tips(self, attribute_name, annotation_pairs,
                           label_attribute='label', update=False):
        """Annotates the tips of the tree

        Deprecated:
            * Update to use annotate_tree

        Args:
            attribute_name : The name of the annotation attribute to add
            annotation_pairs : A dictionary of label keys with annotation
                values
            label_attribute : If this is provided, use this annotation
                attribute as the key instead of the label
        """
        label_method = self._get_label_method(label_attribute)

        for taxon in self.taxon_namespace:
            try:
                # label = getattr(taxon, labelAttribute)
                label = label_method(taxon)

                if taxon.annotations.get_value(attribute_name) is not None:
                    if update:
                        # Remove existing values
                        for ann in taxon.annotations.findall(
                                                        name=attribute_name):
                            taxon.annotations.remove(ann)
                        # Set new value
                        taxon.annotations.add_new(attribute_name,
                                                  annotation_pairs[label])
                else:
                    taxon.annotations.add_new(attribute_name,
                                              annotation_pairs[label])
            except KeyError:
                # Pass if label is not found in the dictionary, otherwise fail
                pass

    # ..............................
    def get_annotations(self, annotation_attribute):
        """Gets a list of (label, annotation) pairs

        Args:
            annotation_attribute : The annotation attribute to retrieve
        """
        annotations = []
        for taxon in self.taxon_namespace:
            att = taxon.annotations.get_value(annotation_attribute)
            annotations.append((taxon.label, att))
        return annotations

    # ..............................
    def get_distance_matrix(self, label_attribute='label',
                            ordered_labels=None):
        """Gets a Matrix object of phylogenetic distances

        Get a Matrix object of phylogenetic distances between tips using a
        lower memory footprint

        Args:
            label_attribute : The attribute of the tips to use as labels for
                the matrix
            ordered_labels : If provided, use this order of labels
        """
        label_method = self._get_label_method(label_attribute)

        # Get list of labels
        if ordered_labels is None:
            ordered_labels = []
            for taxon in self.taxon_namespace:
                ordered_labels.append(label_method(taxon))

        label_lookup = dict([(
                ordered_labels[i], i) for i in range(len(ordered_labels))])

        dist_mtx = np.zeros((len(ordered_labels), len(ordered_labels)),
                            dtype=float)

        # Build path lookup dictionary
        path_lookups = {}
        for taxon in self.taxon_namespace:
            n = self.find_node_for_taxon(taxon)
            l = []
            while n is not None:
                if n.edge_length is not None:
                    # If this is still too big, drop id and do some logic with
                    #    lengths
                    l.append((id(n), n.edge_length))
                n = n.parent_node
            path_lookups[taxon.label] = l

        num_taxa = len(self.taxon_namespace)
        for i_1 in range(num_taxa - 1):
            taxon1 = self.taxon_namespace[i_1]

            label = label_method(taxon1)
            # Check for matrix index
            idx1 = label_lookup[label]

            # Build path to root for taxon 1
            # path_labels = []
            o_dist = 0.0
            t_path = path_lookups[taxon1.label]
            t_labels = []
            for label, p_dist in t_path:
                o_dist += p_dist
                t_labels.append(label)

            for i_2 in range(i_1, num_taxa):
                taxon2 = self.taxon_namespace[i_2]

                idx2 = label_lookup[label_method(taxon2)]

                # Initialize distance for these two taxa
                dist = o_dist

                # Loop through path back to root
                t2_path = path_lookups[taxon2.label]

                for label, p_dist in t2_path:
                    if label in t_labels:
                        dist -= p_dist
                    else:
                        dist += p_dist

                # mrca = pdm.mrca(taxon1, taxon2)
                # dist = pdm.patristic_distance(taxon1, taxon2)
                dist_mtx[idx1, idx2] = dist
                dist_mtx[idx2, idx1] = dist

        distance_matrix = Matrix(dist_mtx, headers={'0': ordered_labels,
                                                    '1': ordered_labels})
        return distance_matrix

    # ..............................
    def get_distance_matrix_dendropy(self, label_attribute='label',
                                     ordered_labels=None):
        """Gets a Matrix object of phylogenetic distances between tips

        Args:
            label_attribute : The attribute of the tips to use as labels for
                the matrix
            ordered_labels : If provided, use this order of labels
        """
        label_method = self._get_label_method(label_attribute)

        # Get list of labels
        if ordered_labels is None:
            ordered_labels = []
            for taxon in self.taxon_namespace:
                ordered_labels.append(label_method(taxon))

        label_lookup = dict([(
                ordered_labels[i], i) for i in range(len(ordered_labels))])

        dist_mtx = np.zeros((len(ordered_labels), len(ordered_labels)),
                            dtype=float)

        pdm = self.phylogenetic_distance_matrix()

        for taxon1 in self.taxon_namespace:
            label = label_method(taxon1)
            # Check for matrix index
            idx1 = label_lookup[label]

            for taxon2 in self.taxon_namespace:
                idx2 = label_lookup[label_method(taxon2)]
                # mrca = pdm.mrca(taxon1, taxon2)
                dist = pdm.patristic_distance(taxon1, taxon2)
                dist_mtx[idx1, idx2] = dist

        distance_matrix = Matrix(dist_mtx, headers={'0': ordered_labels,
                                                    '1': ordered_labels})
        return distance_matrix

    # ..............................
    def get_labels(self):
        """Gets tip labels for a clade

        Note:
            * Bottom-up order
        """
        labels = []
        for taxon in self.taxon_namespace:
            labels.append(taxon.label)

        labels.reverse()
        return labels

    # ..............................
    def get_variance_covariance_matrix(self, label_attribute='label',
                                       ordered_labels=None):
        """Gets a Matrix object of variance / covariance for tips in tree

        Args:
            label_attribute : The attribute of the tips to use as labels for
                the matrix
            ordered_labels : If provided, use this order of labels
        """
        if not self.has_branch_lengths():
            raise LmTreeException('Cannot create VCV without branch lengths')

        label_method = self._get_label_method(label_attribute)

        # Get list of labels
        if ordered_labels is None:
            ordered_labels = []
            for taxon in self.taxon_namespace:
                ordered_labels.append(label_method(taxon))

        label_lookup = dict([(
                ordered_labels[i], i) for i in range(len(ordered_labels))])

        n = len(ordered_labels)
        vcv = np.zeros((n, n), dtype=float)

        edges = []
        for edge in self.postorder_edge_iter():
            edges.append(edge)

        edges.reverse()

        for edge in edges:
            # TODO: Evaluate if el assignment can throw error
            el = edge.head_node.distance_from_root()
            if el is not None:
                child_nodes = edge.head_node.child_nodes()
                if len(child_nodes) == 0:
                    idx = label_lookup[label_method(edge.head_node.taxon)]
                    vcv[idx, idx] = edge.head_node.distance_from_root()
                else:
                    left_child, right_child = edge.head_node.child_nodes()
                    left_tips = [
                        label_lookup[
                            label_method(tip_node.taxon)
                                    ] for tip_node in left_child.leaf_nodes()]
                    right_tips = [
                        label_lookup[
                            label_method(tip_node.taxon)
                                    ] for tip_node in right_child.leaf_nodes()]
                    # if len(leftTips) > 1 and len(rightTips) > 1:
                    for l in left_tips:
                        for r in right_tips:
                            vcv[l, r] = vcv[r, l] = el

            for node in self.leaf_nodes():
                idx = label_lookup[label_method(node.taxon)]
                vcv[idx, idx] = node.distance_from_root()

        vcv_matrix = Matrix(vcv, headers={'0': ordered_labels,
                                          '1': ordered_labels})
        return vcv_matrix

    # ..............................
    def has_branch_lengths(self):
        """Returns a boolean indicating if the entire tree has branch lengths
        """
        try:
            self.minmax_leaf_distance_from_root()
            return True
        except:
            return False

    # ..............................
    def has_polytomies(self):
        """Returns boolean indicating if the tree has polytomies
        """
        for n in self.nodes():
            if len(n.child_nodes()) > 2:
                return True
        return False

    # ..............................
    def is_binary(self):
        """Checks if the tree is binary

        Note:
            * Checks that every clade has either zero or two children
        """
        for n in self.nodes():
            if not len(n.child_nodes()) in [0, 2]:
                return False
        return True

    # ..............................
    def is_ultrametric(self, rel_tol=1e-03):
        """Checks if the tree is ultrametric

        Args:
            rel_tol : The relative tolerance to determine if the min and max
                are equal.  We will say they are equal if they are 99.9%.

        Note:
            * To be ultrametric, the branch length from root to tip must be
                equal for all tips
        """
        try:
            min_bl, max_bl = self.minmax_leaf_distance_from_root()
            return np.isclose(min_bl, max_bl, rtol=rel_tol)
        except:
            pass
        return False

    # ..............................
    def prune_tips_without_attribute(self,
                                     search_attribute=PhyloTreeKeys.MTX_IDX):
        """Prunes the tree of any tips that don't have the specified attribute
        """
        prune_taxa = []
        for taxon in self.taxon_namespace:
            val = taxon.annotations.get_value(search_attribute)
            if val is None:
                prune_taxa.append(taxon)
        self.prune_taxa(prune_taxa)
        self.purge_taxon_namespace()

    # ..............................
    def _annotation_method(self, label_attribute):
        """Use the label attribute as the node label
        """
        def label_method(taxon):
            return taxon.annotations.get_value(label_attribute)
        return label_method

    # ..............................
    def _annotate_node(self, node, annotation_attribute, annotation_value,
                       update=False):
        """Annotates a node with the given value

        Args:
            node: A node to add an annotation to
            annotation_attribute: The annotation attribute to add.  If None or
                'label', update the node label
            annotation_value: The value of the annotation
            update (:obj:`bool`, optional): If True, update existing attribute
        """
        if annotation_attribute is None or \
                annotation_attribute.lower() == 'label':
            try:
                node.taxon.label = annotation_value
            except:
                node.label = annotation_value
        else:
            if node.annotations.get_value(annotation_attribute) is not None:
                if update:
                    # Remove existing annotations
                    for ann in node.annotations.findall(
                            name=annotation_attribute):
                        node.annotations.remove(ann)
                    node.annotations.add_new(
                        annotation_attribute, annotation_value)
            else:
                node.annotations.add_new(
                    annotation_attribute, annotation_value)

    # ..............................
    def _get_label_method(self, label_attribute):
        """Gets the function to be used for retrieving labels
        """
        if label_attribute is None or label_attribute.lower() == 'label':
            return self._label_method
        else:
            return self._annotation_method(label_attribute)

    # ..............................
    def _label_tree_nodes(self, node, i, prefix=None, overwrite=False):
        """Private function to do the work when labeling nodes

        Note:
            * Recursive
        """
        cn = node.child_nodes()

        # If we have children, label and recurse
        if len(cn) > 0:
            if node.label is None or overwrite:
                if prefix is not None:
                    node.label = '{}{}'.format(prefix, i)
                else:
                    node.label = str(i)
                i += 1
            # Loop through children and label nodes
            for child in cn:
                i = self._label_tree_nodes(child, i, prefix=prefix,
                                           overwrite=overwrite)
        # Return the current i value
        return i

    # ..............................
    def _label_method(self, node):
        """Use the label of the node or taxon for the label
        """
        # If the node (or taxon) has a label, return it
        if node.label is not None:
            return node.label
        else:
            # Try to return the label of the taxon object if it has one
            try:
                return node.taxon.label
            except:
                # Fall back to returning None
                return None
