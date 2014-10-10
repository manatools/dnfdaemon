import xml.etree.ElementTree as etree

tree = etree.parse('dnf-system.xml')
root = tree.getroot()
for node in root:
    if node.get('name') == 'org.baseurl.DnfSystem':
       for method in node:
           print('.. py:function:: {}'.format(method.get('name')))
           for arg in method:
               #print('  ',arg.attrib)
               arg_dir = arg.get('direction')
               if arg_dir == 'in':
                   arg_name = arg.get('name')
                   arg_type = arg.get('type')
                   print('   :param {}: '.format(arg_name) )
                   print('   :ptype {}: '.format(arg_type) )
               else:
                   arg_type = arg.get('type')
                   print('   :return:') 
                   print('   :rtype: {}\n'.format(arg_type)) 
                   

