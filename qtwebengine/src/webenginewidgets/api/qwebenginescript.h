/****************************************************************************
**
** Copyright (C) 2015 The Qt Company Ltd.
** Contact: http://www.qt.io/licensing/
**
** This file is part of the QtWebEngine module of the Qt Toolkit.
**
** $QT_BEGIN_LICENSE:LGPL$
** Commercial License Usage
** Licensees holding valid commercial Qt licenses may use this file in
** accordance with the commercial license agreement provided with the
** Software or, alternatively, in accordance with the terms contained in
** a written agreement between you and The Qt Company. For licensing terms
** and conditions see http://www.qt.io/terms-conditions. For further
** information use the contact form at http://www.qt.io/contact-us.
**
** GNU Lesser General Public License Usage
** Alternatively, this file may be used under the terms of the GNU Lesser
** General Public License version 3 as published by the Free Software
** Foundation and appearing in the file LICENSE.LGPLv3 included in the
** packaging of this file. Please review the following information to
** ensure the GNU Lesser General Public License version 3 requirements
** will be met: https://www.gnu.org/licenses/lgpl.html.
**
** GNU General Public License Usage
** Alternatively, this file may be used under the terms of the GNU
** General Public License version 2.0 or later as published by the Free
** Software Foundation and appearing in the file LICENSE.GPL included in
** the packaging of this file. Please review the following information to
** ensure the GNU General Public License version 2.0 requirements will be
** met: http://www.gnu.org/licenses/gpl-2.0.html.
**
** $QT_END_LICENSE$
**
****************************************************************************/

#ifndef QWEBENGINESCRIPT_H
#define QWEBENGINESCRIPT_H
#include "qtwebenginewidgetsglobal.h"

#include <QtCore/QSharedDataPointer>
#include <QtCore/QString>

namespace QtWebEngineCore {
class UserScript;
} // namespace

QT_BEGIN_NAMESPACE

class QWEBENGINEWIDGETS_EXPORT QWebEngineScript {
public:
    enum InjectionPoint {
        Deferred,
        DocumentReady,
        DocumentCreation
    };

    enum ScriptWorldId {
        MainWorld = 0,
        ApplicationWorld,
        UserWorld
    };

    QWebEngineScript();
    QWebEngineScript(const QWebEngineScript &other);
    ~QWebEngineScript();

    QWebEngineScript &operator=(const QWebEngineScript &other);

    bool isNull() const;

    QString name() const;
    void setName(const QString &);

    QString sourceCode() const;
    void setSourceCode(const QString &);

    InjectionPoint injectionPoint() const;
    void setInjectionPoint(InjectionPoint);

    quint32 worldId() const;
    void setWorldId(quint32);

    bool runsOnSubFrames() const;
    void setRunsOnSubFrames(bool on);

    bool operator==(const QWebEngineScript &other) const;
    inline bool operator!=(const QWebEngineScript &other) const
    { return !operator==(other); }
    void swap(QWebEngineScript &other) { qSwap(d, other.d); }


private:
    friend class QWebEngineScriptCollectionPrivate;
    friend class QWebEngineScriptCollection;
    QWebEngineScript(const QtWebEngineCore::UserScript &);

    QSharedDataPointer<QtWebEngineCore::UserScript> d;
};

Q_DECLARE_SHARED(QWebEngineScript)

#ifndef QT_NO_DEBUG_STREAM
QWEBENGINEWIDGETS_EXPORT QDebug operator<<(QDebug, const QWebEngineScript &);
#endif

QT_END_NAMESPACE

#endif // QWEBENGINESCRIPT_H
