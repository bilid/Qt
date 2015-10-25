# Copyright (c) 2012 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Helper functions for the layout test analyzer."""

from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import fileinput
import os
import pickle
import re
import smtplib
import socket
import sys
import time

from bug import Bug
from test_expectations_history import TestExpectationsHistory

DEFAULT_TEST_EXPECTATION_PATH = ('trunk/LayoutTests/TestExpectations')
LEGACY_DEFAULT_TEST_EXPECTATION_PATH = (
    'trunk/LayoutTests/platform/chromium/test_expectations.txt')
REVISION_LOG_URL = ('http://build.chromium.org/f/chromium/perf/dashboard/ui/'
    'changelog_blink.html?url=/trunk/LayoutTests/%s&range=%d:%d')
DEFAULT_REVISION_VIEW_URL = 'http://src.chromium.org/viewvc/blink?revision=%s'


class AnalyzerResultMap:
  """A class to deal with joined result produed by the analyzer.

  The join is done between layouttests and the test_expectations object
  (based on the test expectation file). The instance variable |result_map|
  contains the following keys: 'whole','skip','nonskip'. The value of 'whole'
  contains information about all layouttests. The value of 'skip' contains
  information about skipped layouttests where it has 'SKIP' in its entry in
  the test expectation file. The value of 'nonskip' contains all information
  about non skipped layout tests, which are in the test expectation file but
  not skipped. The information is exactly same as the one parsed by the
  analyzer.
  """

  def __init__(self, test_info_map):
    """Initialize the AnalyzerResultMap based on test_info_map.

    Test_info_map contains all layouttest information. The job here is to
    classify them as 'whole', 'skip' or 'nonskip' based on that information.

    Args:
      test_info_map: the result map of |layouttests.JoinWithTestExpectation|.
          The key of the map is test name such as 'media/media-foo.html'.
          The value of the map is a map that contains the following keys:
          'desc'(description), 'te_info' (test expectation information),
          which is a list of test expectation information map. The key of the
          test expectation information map is test expectation keywords such
          as "SKIP" and other keywords (for full list of keywords, please
          refer to |test_expectations.ALL_TE_KEYWORDS|).
    """
    self.result_map = {}
    self.result_map['whole'] = {}
    self.result_map['skip'] = {}
    self.result_map['nonskip'] = {}
    if test_info_map:
      for (k, value) in test_info_map.iteritems():
        self.result_map['whole'][k] = value
        if 'te_info' in value:
          # Don't count SLOW PASS, WONTFIX, or ANDROID tests as failures.
          if any([True for x in value['te_info'] if set(x.keys()) ==
                  set(['SLOW', 'PASS', 'Bugs', 'Comments', 'Platforms']) or
                  'WONTFIX' in x or x['Platforms'] == ['ANDROID']]):
            continue
          if any([True for x in value['te_info'] if 'SKIP' in x]):
            self.result_map['skip'][k] = value
          else:
            self.result_map['nonskip'][k] = value

  @staticmethod
  def GetDiffString(diff_map_element, type_str):
    """Get difference string out of diff map element.

    The difference string shows difference between two analyzer results
    (for example, a result for now and a result for sometime in the past)
    in HTML format (with colors). This is used for generating email messages.

    Args:
      diff_map_element: An element of the compared map generated by
          |CompareResultMaps()|. The element has two lists of test cases. One
          is for test names that are in the current result but NOT in the
          previous result. The other is for test names that are in the previous
          results but NOT in the current result. Please refer to comments in
          |CompareResultMaps()| for details.
      type_str: a string indicating the test group to which |diff_map_element|
          belongs; used for color determination.  Must be 'whole', 'skip', or
          'nonskip'.

    Returns:
      a string in HTML format (with colors) to show difference between two
          analyzer results.
    """
    if not diff_map_element[0] and not diff_map_element[1]:
      return 'No Change'
    color = ''
    diff = len(diff_map_element[0]) - len(diff_map_element[1])
    if diff > 0 and type_str != 'whole':
      color = 'red'
    else:
      color = 'green'
    diff_sign = ''
    if diff > 0:
      diff_sign = '+'
    if not diff:
      whole_str = 'No Change'
    else:
      whole_str = '<font color="%s">%s%d</font>' % (color, diff_sign, diff)
    colors = ['red', 'green']
    if type_str == 'whole':
      # Bug 107773 - when we increase the number of tests,
      # the name of the tests are in red, it should be green
      # since it is good thing.
      colors = ['green', 'red']
    str1 = ''
    for (name, _) in diff_map_element[0]:
      str1 += '<font color="%s">%s,</font>' % (colors[0], name)
    str2 = ''
    for (name, _) in diff_map_element[1]:
      str2 += '<font color="%s">%s,</font>' % (colors[1], name)
    if str1 or str2:
      whole_str += ':'
    if str1:
      whole_str += str1
    if str2:
      whole_str += str2
    # Remove the last occurrence of ','.
    whole_str = ''.join(whole_str.rsplit(',', 1))
    return whole_str

  def GetPassingRate(self):
    """Get passing rate.

    Returns:
      layout test passing rate of this result in percent.

    Raises:
      ValueEror when the number of tests in test group "whole" is equal
          or less than that of "skip".
    """
    delta = len(self.result_map['whole'].keys()) - (
        len(self.result_map['skip'].keys()))
    if delta <= 0:
      raise ValueError('The number of tests in test group "whole" is equal or '
                       'less than that of "skip"')
    return 100 - len(self.result_map['nonskip'].keys()) * 100.0 / delta

  def ConvertToCSVText(self, current_time):
    """Convert |self.result_map| into stats and issues text in CSV format.

    Both are used as inputs for Google spreadsheet.

    Args:
      current_time: a string depicting a time in year-month-day-hour
        format (e.g., 2011-11-08-16).

    Returns:
      a tuple of stats and issues_txt
      stats: analyzer result in CSV format that shows:
          (current_time, the number of tests, the number of skipped tests,
           the number of failing tests, passing rate)
          For example,
            "2011-11-10-15,204,22,12,94"
       issues_txt: issues listed in CSV format that shows:
          (BUGWK or BUGCR, bug number, the test expectation entry,
           the name of the test)
          For example,
            "BUGWK,71543,TIMEOUT PASS,media/media-element-play-after-eos.html,
             BUGCR,97657,IMAGE CPU MAC TIMEOUT PASS,media/audio-repaint.html,"
    """
    stats = ','.join([current_time, str(len(self.result_map['whole'].keys())),
                      str(len(self.result_map['skip'].keys())),
                      str(len(self.result_map['nonskip'].keys())),
                      str(self.GetPassingRate())])
    issues_txt = ''
    for bug_txt, test_info_list in (
        self.GetListOfBugsForNonSkippedTests().iteritems()):
      matches = re.match(r'(BUG(CR|WK))(\d+)', bug_txt)
      bug_suffix = ''
      bug_no = ''
      if matches:
        bug_suffix = matches.group(1)
        bug_no = matches.group(3)
      issues_txt += bug_suffix + ',' + bug_no + ','
      for test_info in test_info_list:
        test_name, te_info = test_info
        issues_txt += ' '.join(te_info.keys()) + ',' + test_name + ','
      issues_txt += '\n'
    return stats, issues_txt

  def ConvertToString(self, prev_time, diff_map, issue_detail_mode):
    """Convert this result to HTML display for email.

    Args:
      prev_time: the previous time string that are compared against.
      diff_map: the compared map generated by |CompareResultMaps()|.
      issue_detail_mode: includes the issue details in the output string if
          this is True.

    Returns:
      a analyzer result string in HTML format.
    """
    return_str = ''
    if diff_map:
      return_str += (
          '<b>Statistics (Diff Compared to %s):</b><ul>'
          '<li>The number of tests: %d (%s)</li>'
          '<li>The number of failing skipped tests: %d (%s)</li>'
          '<li>The number of failing non-skipped tests: %d (%s)</li>'
          '<li>Passing rate: %.2f %%</li></ul>') % (
              prev_time, len(self.result_map['whole'].keys()),
              AnalyzerResultMap.GetDiffString(diff_map['whole'], 'whole'),
              len(self.result_map['skip'].keys()),
              AnalyzerResultMap.GetDiffString(diff_map['skip'], 'skip'),
              len(self.result_map['nonskip'].keys()),
              AnalyzerResultMap.GetDiffString(diff_map['nonskip'], 'nonskip'),
              self.GetPassingRate())
    if issue_detail_mode:
      return_str += '<b>Current issues about failing non-skipped tests:</b>'
      for (bug_txt, test_info_list) in (
          self.GetListOfBugsForNonSkippedTests().iteritems()):
        return_str += '<ul>%s' % Bug(bug_txt)
        for test_info in test_info_list:
          (test_name, te_info) = test_info
          gpu_link = ''
          if 'GPU' in te_info:
            gpu_link = 'group=%40ToT%20GPU%20Mesa%20-%20chromium.org&'
          dashboard_link = ('http://test-results.appspot.com/dashboards/'
                            'flakiness_dashboard.html#%stests=%s') % (
                                gpu_link, test_name)
          return_str += '<li><a href="%s">%s</a> (%s) </li>' % (
              dashboard_link, test_name, ' '.join(
                  [key for key in te_info.keys() if key != 'Platforms']))
        return_str += '</ul>\n'
    return return_str

  def CompareToOtherResultMap(self, other_result_map):
    """Compare this result map with the other to see if there are any diff.

    The comparison is done for layouttests which belong to 'whole', 'skip',
    or 'nonskip'.

    Args:
      other_result_map: another result map to be compared against the result
          map of the current object.

    Returns:
      a map that has 'whole', 'skip' and 'nonskip' as keys.
          Please refer to |diff_map| in |SendStatusEmail()|.
    """
    comp_result_map = {}
    for name in ['whole', 'skip', 'nonskip']:
      if name == 'nonskip':
        # Look into expectation to get diff only for non-skipped tests.
        lookIntoTestExpectationInfo = True
      else:
        #  Otherwise, only test names are compared to get diff.
        lookIntoTestExpectationInfo = False
      comp_result_map[name] = GetDiffBetweenMaps(
          self.result_map[name], other_result_map.result_map[name],
          lookIntoTestExpectationInfo)
    return comp_result_map

  @staticmethod
  def Load(file_path):
    """Load the object from |file_path| using pickle library.

    Args:
      file_path: the string path to the file from which to read the result.

    Returns:
       a AnalyzerResultMap object read from |file_path|.
    """
    file_object = open(file_path)
    analyzer_result_map = pickle.load(file_object)
    file_object.close()
    return analyzer_result_map

  def Save(self, file_path):
    """Save the object to |file_path| using pickle library.

    Args:
       file_path: the string path to the file in which to store the result.
    """
    file_object = open(file_path, 'wb')
    pickle.dump(self, file_object)
    file_object.close()

  def GetListOfBugsForNonSkippedTests(self):
    """Get a list of bugs for non-skipped layout tests.

    This is used for generating email content.

    Returns:
        a mapping from bug modifier text (e.g., BUGCR1111) to a test name and
            main test information string which excludes comments and bugs.
            This is used for grouping test names by bug.
    """
    bug_map = {}
    for (name, value) in self.result_map['nonskip'].iteritems():
      for te_info in value['te_info']:
        main_te_info = {}
        for k in te_info.keys():
          if k != 'Comments' and k != 'Bugs':
            main_te_info[k] = True
        if 'Bugs' in te_info:
          for bug in te_info['Bugs']:
            if bug not in bug_map:
              bug_map[bug] = []
            bug_map[bug].append((name, main_te_info))
    return bug_map


def SendStatusEmail(prev_time, analyzer_result_map, diff_map,
                    receiver_email_address, test_group_name,
                    appended_text_to_email, email_content, rev_str,
                    email_only_change_mode):
  """Send status email.

  Args:
    prev_time: the date string such as '2011-10-09-11'. This format has been
        used in this analyzer.
    analyzer_result_map: current analyzer result.
    diff_map: a map that has 'whole', 'skip' and 'nonskip' as keys.
        The values of the map are the result of |GetDiffBetweenMaps()|.
        The element has two lists of test cases. One (with index 0) is for
        test names that are in the current result but NOT in the previous
        result. The other (with index 1) is for test names that are in the
        previous results but NOT in the current result.
         For example (test expectation information is omitted for
         simplicity),
           comp_result_map['whole'][0] = ['foo1.html']
           comp_result_map['whole'][1] = ['foo2.html']
         This means that current result has 'foo1.html' but it is NOT in the
         previous result. This also means the previous result has 'foo2.html'
         but it is NOT in the current result.
    receiver_email_address: receiver's email address.
    test_group_name: string representing the test group name (e.g., 'media').
    appended_text_to_email: a text which is appended at the end of the status
        email.
    email_content: an email content string that will be shown on the dashboard.
    rev_str: a revision string that contains revision information that is sent
        out in the status email. It is obtained by calling
        |GetRevisionString()|.
    email_only_change_mode: send email only when there is a change if this is
        True. Otherwise, always send email after each run.
  """
  if rev_str:
    email_content += '<br><b>Revision Information:</b>'
    email_content += rev_str
  localtime = time.asctime(time.localtime(time.time()))
  change_str = ''
  if email_only_change_mode:
    change_str = 'Status Change '
  subject = 'Layout Test Analyzer Result %s(%s): %s' % (change_str,
                                                        test_group_name,
                                                        localtime)
  SendEmail('no-reply@chromium.org', [receiver_email_address],
            subject, email_content + appended_text_to_email)


def GetRevisionString(prev_time, current_time, diff_map):
  """Get a string for revision information during the specified time period.

  Args:
    prev_time: the previous time as a floating point number expressed
        in seconds since the epoch, in UTC.
    current_time: the current time as a floating point number expressed
        in seconds since the epoch, in UTC. It is typically obtained by
        time.time() function.
    diff_map: a map that has 'whole', 'skip' and 'nonskip' as keys.
        Please refer to |diff_map| in |SendStatusEmail()|.

  Returns:
    a tuple of strings:
        1) full string containing links, author, date, and line for each
           change in the test expectation file.
        2) shorter string containing only links to the change.  Used for
           trend graph annotations.
        3) last revision number for the given test group.
        4) last revision date for the given test group.
  """
  if not diff_map:
    return ('', '', '', '')
  testname_map = {}
  for test_group in ['skip', 'nonskip']:
    for i in range(2):
      for (k, _) in diff_map[test_group][i]:
        testname_map[k] = True
  rev_infos = TestExpectationsHistory.GetDiffBetweenTimes(prev_time,
                                                          current_time,
                                                          testname_map.keys())
  rev_str = ''
  simple_rev_str = ''
  rev = ''
  rev_date = ''
  if rev_infos:
    # Get latest revision number and date.
    rev = rev_infos[-1][1]
    rev_date = rev_infos[-1][3]
    for rev_info in rev_infos:
      (old_rev, new_rev, author, date, _, target_lines) = rev_info

      # test_expectations.txt was renamed to TestExpectations at r119317.
      new_path = DEFAULT_TEST_EXPECTATION_PATH
      if new_rev < 119317:
        new_path = LEGACY_DEFAULT_TEST_EXPECTATION_PATH
      old_path = DEFAULT_TEST_EXPECTATION_PATH
      if old_rev < 119317:
        old_path = LEGACY_DEFAULT_TEST_EXPECTATION_PATH

      link = REVISION_LOG_URL % (new_path, old_rev, new_rev)
      rev_str += '<ul><a href="%s">%s->%s</a>\n' % (link, old_rev, new_rev)
      simple_rev_str = '<a href="%s">%s->%s</a>,' % (link, old_rev, new_rev)
      rev_str += '<li>%s</li>\n' % author
      rev_str += '<li>%s</li>\n<ul>' % date
      for line in target_lines:
        # Find *.html pattern (test name) and replace it with the link to
        # flakiness dashboard.
        test_name_pattern = r'(\S+.html)'
        match = re.search(test_name_pattern, line)
        if match:
          test_name = match.group(1)
          gpu_link = ''
          if 'GPU' in line:
            gpu_link = 'group=%40ToT%20GPU%20Mesa%20-%20chromium.org&'
          dashboard_link = ('http://test-results.appspot.com/dashboards/'
                            'flakiness_dashboard.html#%stests=%s') % (
                                gpu_link, test_name)
          line = line.replace(test_name, '<a href="%s">%s</a>' % (
              dashboard_link, test_name))
        # Find bug text and replace it with the link to the bug.
        bug = Bug(line)
        if bug.bug_txt:
          line = '<li>%s</li>\n' % line.replace(bug.bug_txt, str(bug))
        rev_str += line
      rev_str += '</ul></ul>'
  return (rev_str, simple_rev_str, rev, rev_date)


def SendEmail(sender_email_address, receivers_email_addresses, subject,
              message):
  """Send email using localhost's mail server.

  Args:
    sender_email_address: sender's email address.
    receivers_email_addresses: receiver's email addresses.
    subject: subject string.
    message: email message.
  """
  try:
    html_top = """
      <html>
      <head></head>
      <body>
    """
    html_bot = """
      </body>
      </html>
    """
    html = html_top + message + html_bot
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = sender_email_address
    msg['To'] = receivers_email_addresses[0]
    part1 = MIMEText(html, 'html')
    smtp_obj = smtplib.SMTP('localhost')
    msg.attach(part1)
    smtp_obj.sendmail(sender_email_address, receivers_email_addresses,
                      msg.as_string())
    print 'Successfully sent email'
  except smtplib.SMTPException, ex:
    print 'Authentication failed:', ex
    print 'Error: unable to send email'
  except (socket.gaierror, socket.error, socket.herror), ex:
    print ex
    print 'Error: unable to send email'


def FindLatestTime(time_list):
  """Find latest time from |time_list|.

  The current status is compared to the status of the latest file in
  |RESULT_DIR|.

  Args:
    time_list: a list of time string in the form of 'Year-Month-Day-Hour'
        (e.g., 2011-10-23-23). Strings not in this format are ignored.

  Returns:
     a string representing latest time among the time_list or None if
         |time_list| is empty or no valid date string in |time_list|.
  """
  if not time_list:
    return None
  latest_date = None
  for time_element in time_list:
    try:
      item_date = datetime.strptime(time_element, '%Y-%m-%d-%H')
      if latest_date is None or latest_date < item_date:
        latest_date = item_date
    except ValueError:
      # Do nothing.
      pass
  if latest_date:
    return latest_date.strftime('%Y-%m-%d-%H')
  else:
    return None


def ReplaceLineInFile(file_path, search_exp, replace_line):
  """Replace line which has |search_exp| with |replace_line| within a file.

  Args:
      file_path: the file that is being replaced.
      search_exp: search expression to find a line to be replaced.
      replace_line: the new line.
  """
  for line in fileinput.input(file_path, inplace=1):
    if search_exp in line:
      line = replace_line
    sys.stdout.write(line)


def FindLatestResult(result_dir):
  """Find the latest result in |result_dir| and read and return them.

  This is used for comparison of analyzer result between current analyzer
  and most known latest result.

  Args:
    result_dir: the result directory.

  Returns:
    A tuple of filename (latest_time) and the latest analyzer result.
        Returns None if there is no file or no file that matches the file
        patterns used ('%Y-%m-%d-%H').
  """
  dir_list = os.listdir(result_dir)
  file_name = FindLatestTime(dir_list)
  if not file_name:
    return None
  file_path = os.path.join(result_dir, file_name)
  return (file_name, AnalyzerResultMap.Load(file_path))


def GetDiffBetweenMaps(map1, map2, lookIntoTestExpectationInfo=False):
  """Get difference between maps.

  Args:
    map1: analyzer result map to be compared.
    map2: analyzer result map to be compared.
    lookIntoTestExpectationInfo: a boolean to indicate whether to compare
        test expectation information in addition to just the test case names.

  Returns:
    a tuple of |name1_list| and |name2_list|. |Name1_list| contains all test
        name and the test expectation information in |map1| but not in |map2|.
        |Name2_list| contains all test name and the test expectation
        information in |map2| but not in |map1|.
  """

  def GetDiffBetweenMapsHelper(map1, map2, lookIntoTestExpectationInfo):
    """A helper function for GetDiffBetweenMaps.

    Args:
      map1: analyzer result map to be compared.
      map2: analyzer result map to be compared.
      lookIntoTestExpectationInfo: a boolean to indicate whether to compare
        test expectation information in addition to just the test case names.

    Returns:
      a list of tuples (name, te_info) that are in |map1| but not in |map2|.
    """
    name_list = []
    for (name, value1) in map1.iteritems():
      if name in map2:
        if lookIntoTestExpectationInfo and 'te_info' in value1:
          list1 = value1['te_info']
          list2 = map2[name]['te_info']
          te_diff = [item for item in list1 if not item in list2]
          if te_diff:
            name_list.append((name, te_diff))
      else:
        name_list.append((name, value1))
    return name_list

  return (GetDiffBetweenMapsHelper(map1, map2, lookIntoTestExpectationInfo),
          GetDiffBetweenMapsHelper(map2, map1, lookIntoTestExpectationInfo))